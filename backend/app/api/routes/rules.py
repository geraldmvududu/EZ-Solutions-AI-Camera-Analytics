import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.deps import require_permission, tenant_filter_value
from app.core.permissions import Permissions
from app.database import get_db
from app.models.alert import Alert
from app.models.rule import AIRule
from app.models.user import User
from app.schemas.rule import AIRuleCreate, AIRuleResponse, AIRuleUpdate

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[AIRuleResponse])
def list_rules(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.VIEW_CAMERAS)),
) -> list[AIRule]:
    query = db.query(AIRule)
    tenant_id = tenant_filter_value(user)
    if tenant_id:
        query = query.filter(AIRule.tenant_id == tenant_id)
    return query.order_by(AIRule.created_at.desc()).all()


def _get_owned_rule(db: Session, rule_id: uuid.UUID, user: User) -> AIRule:
    rule = db.get(AIRule, rule_id)
    tenant_id = tenant_filter_value(user)
    if rule is None or (tenant_id and rule.tenant_id != tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


@router.post("", response_model=AIRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: AIRuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> AIRule:
    rule = AIRule(tenant_id=user.tenant_id, **payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_action(db, action="RULE_CREATED", tenant_id=user.tenant_id, user_id=user.id, resource_type="rule", resource_id=str(rule.id), details={"name": rule.name})
    return rule


@router.patch("/{rule_id}", response_model=AIRuleResponse)
def update_rule(
    rule_id: uuid.UUID,
    payload: AIRuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> AIRule:
    rule = _get_owned_rule(db, rule_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    log_action(db, action="RULE_UPDATED", tenant_id=user.tenant_id, user_id=user.id, resource_type="rule", resource_id=str(rule.id))
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permissions.MANAGE_RULES)),
) -> None:
    """Real bug found live on the deployed VM (a genuine alerts_rule_id_fkey
    ForeignKeyViolation): a rule that already matched a real event and created a real
    Alert couldn't be deleted at all — `db.delete(rule)` alone raised an unhandled
    IntegrityError the moment any Alert referenced it. Alert.rule_id is nullable, so
    every Alert this rule ever created is unscoped (not deleted) first — same
    "unscope rather than destroy" treatment cameras.py::delete_camera already gives
    AIRule/Incident: an alert's own history/evidence outlives the rule config that
    happened to generate it."""
    rule = _get_owned_rule(db, rule_id, user)
    db.query(Alert).filter(Alert.rule_id == rule_id).update({"rule_id": None}, synchronize_session=False)
    db.delete(rule)
    db.commit()
    log_action(db, action="RULE_DELETED", tenant_id=user.tenant_id, user_id=user.id, resource_type="rule", resource_id=str(rule_id))
