import json

from django.core.files.base import ContentFile

from .json import ExtendedJSONEncoder

JSON_CONSTANTS = {
    "NaN": float("nan"),
    "-Infinity": float("-inf"),
    "Infinity": float("inf"),
}


class SplitDictionaryHere:
    """Wrapper class for usage with `store_split_dict`.

    This allows to wrap a dictionary such that the function
    `store_split_dict` stores it in a separate file in storage.
    See there for more information.
    """

    def __init__(self, name, dict, supplementary={}):
        """

        Parameters
        ----------
        name : str
            Name of the subdirectionary. This will be used as a file prefix
            when writing this dictionary to JSON
        dict : dict
            The actual dictionary.
        supplementary : dict
            Supplementary dictionary to include only into the split variant.
        """
        self._name = name
        self._dict = dict
        self._supplementary = supplementary

    def __getitem__(self, key):
        return self._dict.__getitem__(key)

    def __setitem__(self, key, value):
        return self._dict.__setitem__(key, value)

    @property
    def name(self):
        return self._name

    @property
    def dict(self):
        return self._dict

    @property
    def supplementary(self):
        return self._supplementary


def store_split_dict(folder, name, src_dict):
    """Store a dictionary in storage with optional splitting into several files.

    Parameters
    ----------
    folder : topobank.files.models.Folder
        Folder that contains the dictionary files
    name : str
        Determines the files name under which the dict is stored, the extension '.json'
        is appended automatically.
    src_dict : dict
        Dictionary to store, if it contains elements which are instances of
        `SplitDictionaryHere`, the corresponding dictionary is saved into a separate
        file, not in the root file which represents `src_dict`.

    Returns
    -------
    None

    The stored data can be retrieved again from multiple files by using
    `load_split_dict`, given the `storage prefix` and `name` used here to store the
    dict.

    Caution: Don't use the string literals "NaN" and "Infinity" and "-Infinity" as
             values, unless you want them decoded as the corresponding float values.
             This is a workaround for not having NaN in the JSON standard.
    """
    # Traverse dictionary and search for instances of SplitDictionaryHere.
    # Those are written to separate files.

    # We're using our own JSON encoder here, because it represents NaN values as null
    encoder_cls = ExtendedJSONEncoder

    def _split_dict(d):
        if isinstance(d, SplitDictionaryHere):
            split_d = _split_dict(d.dict)
            folder.save_file(
                f"{d.name}.json",
                "der",
                ContentFile(json.dumps(split_d, cls=encoder_cls).encode("utf-8")),
            )
            # Include supplementary dictionary in the toplevel JSON
            return {**{"__external__": f"{d.name}.json"}, **d.supplementary}
        elif hasattr(d, "items"):
            new_d = {}
            for key, value in d.items():
                new_d[key] = _split_dict(value)
            return new_d
        elif isinstance(d, list):
            new_d = []
            for value in d:
                new_d.append(_split_dict(value))
            return new_d
        else:
            return d

    split_d = _split_dict(src_dict)
    folder.save_file(
        f"{name}.json",
        "der",
        ContentFile(json.dumps(split_d, cls=encoder_cls).encode("utf-8")),
    )


def load_split_dict(folder, name):
    """Load split dicts from storage, previously written by `store_split_dict`.

    Parameters
    ----------
    folder : topobank.files.models.Folder
        Folder that contains the dictionary files written by `store_split_dict`.
    name: str
        Name used as parameter of `store_split_dict`.

    Returns
    -------
    Original dict as stored with `store_split_dict`, but without the wrapper classes
    of type `SplitDictionaryHere`.
    """

    def _unsplit_dict(d):
        if hasattr(d, "items"):
            new_d = {}
            for key, value in d.items():
                if key == "__external__":
                    # '__external__' will override anything that is at this level in the dictionary
                    return _unsplit_dict(json.load(folder.open_file(value)))
                new_d[key] = _unsplit_dict(value)
            return new_d
        elif isinstance(d, list):
            new_d = []
            for value in d:
                new_d.append(_unsplit_dict(value))
            return new_d
        elif isinstance(d, str) and (d in JSON_CONSTANTS):
            # reinsert NaN instead of "NaN" (with quotes)
            return JSON_CONSTANTS[d]
        else:
            return d

    d = json.load(folder.open_file(f"{name}.json"))
    return _unsplit_dict(d)


def unsplit_dict(d):
    """Unsplit a dictionary which was split by `store_split_dict`.

    Parameters
    ----------
    d: dict
        Dictionary which was split by `store_split_dict`.

    Returns
    -------
    Original dict as stored with `store_split_dict`, but without the wrapper classes
    of type `SplitDictionaryHere`.
    """
    if isinstance(d, SplitDictionaryHere):
        return unsplit_dict(d.dict)
    elif hasattr(d, "items"):
        new_d = {}
        for key, value in d.items():
            new_d[key] = unsplit_dict(value)
        return new_d
    elif isinstance(d, list):
        new_d = []
        for value in d:
            new_d.append(unsplit_dict(value))
        return new_d
    else:
        return d
