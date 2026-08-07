"""
Identification of data channels by name.

A data file can contain several channels, and which one a measurement refers to
used to be stored as a positional index. That is fragile: when a reader changes
the order in which it reports channels, an existing measurement silently starts
pointing at different data. Channels are therefore identified by *name* here.

Names are not guaranteed to be unique within a file, so an occurrence ordinal
breaks ties. It is a disambiguator rather than part of the identity, and is
recorded *only* when a name matches more than one channel
(:func:`occurrence_for`). A ``None`` ordinal consequently carries an assertion -
"this name identified exactly one channel when it was selected" - so a name that
later becomes ambiguous is reported instead of being resolved to an arbitrary
match.
"""


class ChannelError(Exception):
    """Generic problem while identifying a data channel."""


class ChannelNotFoundError(ChannelError):
    """The recorded channel name does not exist in the data file."""

    def __init__(self, name, occurrence, available):
        self.name = name
        self.occurrence = occurrence
        self.available = list(available)

    def __str__(self):
        wanted = f"'{self.name}'"
        if self.occurrence is not None:
            wanted += f" (occurrence {self.occurrence})"
        available = ", ".join(f"'{name}'" for name in self.available) or "none"
        return (
            f"The data file does not contain a channel {wanted}. Available "
            f"channels: {available}."
        )


class AmbiguousChannelError(ChannelError):
    """The recorded channel name matches several channels in the data file."""

    def __init__(self, name, nb_matches):
        self.name = name
        self.nb_matches = nb_matches

    def __str__(self):
        return (
            f"The channel name '{self.name}' matches {self.nb_matches} channels "
            "in the data file, but it was unambiguous when this measurement was "
            "created. The data file or the reader appears to have changed; "
            "please select the channel again."
        )


class UnsupportedChannelError(ChannelError):
    """No registered measurement type can import this channel."""

    def __init__(self, name, reason=None):
        self.name = name
        self.reason = reason

    def __str__(self):
        s = f"The data channel '{self.name}' is not supported."
        if self.reason:
            s += f" {self.reason}"
        return s


def occurrence_for(names, index):
    """
    Return the occurrence ordinal to record for the channel at `index`.

    Parameters
    ----------
    names : sequence of str
        Names of all channels in the file, in file order.
    index : int
        Position of the selected channel.

    Returns
    -------
    int or None
        ``None`` if the selected name is unique within the file - the common
        case, in which no tie-breaker is needed. Otherwise the 0-based position
        of the channel among the identically-named ones.
    """
    name = names[index]
    matches = [i for i, other in enumerate(names) if other == name]
    if len(matches) < 2:
        return None
    return matches.index(index)


def resolve_channel(names, name, occurrence=None):
    """
    Resolve a channel name to a position in `names`.

    Parameters
    ----------
    names : sequence of str
        Names of all channels in the file, in file order.
    name : str
        Recorded channel name.
    occurrence : int, optional
        Recorded occurrence ordinal. ``None`` asserts that the name was
        unambiguous when it was recorded.

    Returns
    -------
    int
        Position of the matching channel.

    Raises
    ------
    ChannelNotFoundError
        No channel of this name exists, or the ordinal is out of range.
    AmbiguousChannelError
        Several channels match a name that was recorded as unambiguous.
    """
    matches = [i for i, other in enumerate(names) if other == name]
    if len(matches) == 0:
        raise ChannelNotFoundError(name, occurrence, names)
    if len(matches) == 1:
        # A recorded ordinal is redundant here; it is dropped on the next
        # inspection. Deliberately not an error: a file may legitimately have
        # lost a duplicate channel.
        return matches[0]
    if occurrence is None:
        raise AmbiguousChannelError(name, len(matches))
    if occurrence < 0 or occurrence >= len(matches):
        raise ChannelNotFoundError(name, occurrence, names)
    return matches[occurrence]
