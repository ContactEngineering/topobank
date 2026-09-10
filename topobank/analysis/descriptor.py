"""
What topobank knows about a workflow without running it.

A :class:`WorkflowDescriptor` is the part of a workflow that the Django side
needs: its name, how it is displayed, which subjects it accepts, the pydantic
model of its parameters and the files it declares as outputs. Enumeration for
the frontend, validation at submit time, the default parameters and the
de-duplication of results all work on descriptors alone.

How a workflow *runs* is not part of the descriptor. Each workflow manager
(see :mod:`topobank.analysis.managers`) registers its own subclass carrying
whatever its engine needs - the Celery manager's
:class:`~topobank.analysis.celery.workflows.WorkflowImplementation` adds the
in-process implementation methods, their dependencies and a queue; a manager
for another engine adds its own job description. A workflow is therefore tied
to exactly one engine, and the descriptor is the shared vocabulary between
that engine and topobank.
"""

from typing import Union

import pydantic

from .outputs import get_outputs_schema


class WorkflowDescriptor:
    """
    Describes a workflow to topobank. Subclassed by every manager's shim.

    Subclasses set ``Meta.name`` and ``Meta.display_name``, may narrow
    ``Meta.subject_types`` to the subject models the workflow accepts, define
    a ``Parameters`` pydantic model and optionally an ``Outputs`` class (see
    :mod:`topobank.analysis.outputs`).
    """

    class Meta:
        #: Unique, stable identifier, e.g. ``"sds_ml.v3.regression.training"``.
        name: str
        #: Human-readable name for listings.
        display_name: str
        #: Subject model classes this workflow accepts. Managers whose shims
        #: derive this from something else (the Celery manager derives it from
        #: its implementation methods) override :meth:`has_implementation`.
        subject_types = ()

    class Parameters(pydantic.BaseModel):
        model_config = pydantic.ConfigDict(extra="forbid")

    #: Optional outputs declaration - subclasses can define an Outputs class
    Outputs = None

    @classmethod
    def clean_kwargs(cls, kwargs: Union[dict, None], fill_missing: bool = True):
        """
        Validate keyword arguments (parameters) and return validated dictionary

        Parameters
        ----------
        kwargs: Union[dict, None]
            Keyword arguments
        fill_missing: bool, optional
            Fill missing keys with default values. (Default: True)

        Raises
        ------
        pydantic.ValidationError if validation fails
        """
        if kwargs is None:
            if fill_missing:
                return cls.Parameters().model_dump()
            else:
                return {}
        else:
            return cls.Parameters(**kwargs).model_dump(exclude_unset=not fill_missing)

    @classmethod
    def get_default_kwargs(cls) -> dict:
        """Default parameters as a dictionary."""
        return cls.Parameters().model_dump()

    @classmethod
    def get_kwargs_schema(cls) -> dict:
        """JSON schema of the parameters."""
        return cls.Parameters.model_json_schema()

    @classmethod
    def get_outputs_schema(cls) -> list:
        """
        Get JSON schema for declared outputs.

        Returns
        -------
        list
            List of file descriptors with their schemas
        """
        return get_outputs_schema(getattr(cls, "Outputs", None))

    @classmethod
    def has_implementation(cls, model_class) -> bool:
        """Whether this workflow accepts subjects of the given model class."""
        return model_class in cls.Meta.subject_types
