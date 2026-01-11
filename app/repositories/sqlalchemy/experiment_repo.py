"""SQLAlchemy implementation of ExperimentRepository."""

from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

from app.models import Experiment, Variant, Assignment
from app.repositories.interfaces import (
    ExperimentRepository,
    ExperimentEntity,
    ExperimentInput,
    ExperimentUpdateInput,
    VariantEntity,
    AssignmentEntity,
)


class SQLAlchemyExperimentRepository(ExperimentRepository):
    """SQLAlchemy implementation of experiment repository."""

    def __init__(self, session: Session):
        self._session = session

    def _to_variant_entity(self, model: Variant) -> VariantEntity:
        """Convert SQLAlchemy model to entity."""
        return VariantEntity(
            id=model.id,
            experiment_id=model.experiment_id,
            name=model.name,
            traffic_percentage=model.traffic_percentage,
            created_at=model.created_at,
        )

    def _to_experiment_entity(self, model: Experiment) -> ExperimentEntity:
        """Convert SQLAlchemy model to entity."""
        return ExperimentEntity(
            id=model.id,
            name=model.name,
            description=model.description,
            status=model.status,
            created_at=model.created_at,
            variants=[self._to_variant_entity(v) for v in model.variants],
        )

    def _to_assignment_entity(self, model: Assignment) -> AssignmentEntity:
        """Convert SQLAlchemy model to entity."""
        return AssignmentEntity(
            id=model.id,
            experiment_id=model.experiment_id,
            variant_id=model.variant_id,
            user_id=model.user_id,
            assigned_at=model.assigned_at,
            variant_name=model.variant.name,
        )

    def create(self, data: ExperimentInput) -> ExperimentEntity:
        """Create a new experiment with variants."""
        db_experiment = Experiment(
            name=data.name,
            description=data.description,
            status="draft",
        )
        self._session.add(db_experiment)
        self._session.flush()

        for variant_input in data.variants:
            db_variant = Variant(
                experiment_id=db_experiment.id,
                name=variant_input.name,
                traffic_percentage=variant_input.traffic_percentage,
            )
            self._session.add(db_variant)

        self._session.commit()
        self._session.refresh(db_experiment)

        return self._to_experiment_entity(db_experiment)

    def get_by_id(self, experiment_id: int) -> Optional[ExperimentEntity]:
        """Get an experiment by ID."""
        model = (
            self._session.query(Experiment)
            .filter(Experiment.id == experiment_id)
            .first()
        )
        if not model:
            return None
        return self._to_experiment_entity(model)

    def update(
        self, experiment_id: int, data: ExperimentUpdateInput
    ) -> Optional[ExperimentEntity]:
        """Update an experiment."""
        model = (
            self._session.query(Experiment)
            .filter(Experiment.id == experiment_id)
            .first()
        )
        if not model:
            return None

        if data.name is not None:
            model.name = data.name
        if data.description is not None:
            model.description = data.description
        if data.status is not None:
            model.status = data.status

        self._session.commit()
        self._session.refresh(model)

        return self._to_experiment_entity(model)

    def get_variants(self, experiment_id: int) -> list[VariantEntity]:
        """Get all variants for an experiment."""
        models = (
            self._session.query(Variant)
            .filter(Variant.experiment_id == experiment_id)
            .all()
        )
        return [self._to_variant_entity(m) for m in models]

    def get_assignment(
        self, experiment_id: int, user_id: str
    ) -> Optional[AssignmentEntity]:
        """Get existing assignment for a user in an experiment."""
        model = (
            self._session.query(Assignment)
            .filter(
                Assignment.experiment_id == experiment_id,
                Assignment.user_id == user_id,
            )
            .first()
        )
        if not model:
            return None
        return self._to_assignment_entity(model)

    def create_assignment(
        self, experiment_id: int, variant_id: int, user_id: str
    ) -> AssignmentEntity:
        """Create a new assignment."""
        model = Assignment(
            experiment_id=experiment_id,
            variant_id=variant_id,
            user_id=user_id,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)

        return self._to_assignment_entity(model)

    def get_assignments_by_variant(self, variant_id: int) -> list[AssignmentEntity]:
        """Get all assignments for a variant."""
        models = (
            self._session.query(Assignment)
            .filter(Assignment.variant_id == variant_id)
            .all()
        )
        return [self._to_assignment_entity(m) for m in models]
