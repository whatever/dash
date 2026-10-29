# Artifacts Database Schema

## Overview

The artifacts system adds two new tables to store artifact metadata and version history. Both tables integrate with existing dash tables (conversations, messages).

## Tables

### artifacts

Stores metadata for each artifact.

```sql
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 1,
    visibility TEXT NOT NULL DEFAULT 'organization',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX idx_artifacts_conversation ON artifacts(conversation_id);
CREATE INDEX idx_artifacts_created_at ON artifacts(created_at DESC);
```

**Fields:**
- `id`: Unique identifier (nanoid, 21 chars, URL-safe: `proposal-a1b2c3d4e5`)
- `conversation_id`: Optional link to conversation where artifact was created
- `title`: Human-readable title from `<artifact title="...">` tag
- `type`: Content type: 'html', 'markdown', 'react'
- `current_version`: Latest version number (increments on updates)
- `visibility`: 'private', 'organization', 'public' (V1 uses 'organization')
- `created_at`: When artifact was first created
- `updated_at`: When artifact was last modified (any version)

### artifact_versions

Stores content history for each artifact.

```sql
CREATE TABLE artifact_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    UNIQUE(artifact_id, version)
);

CREATE INDEX idx_artifact_versions_artifact ON artifact_versions(artifact_id, version DESC);
```

**Fields:**
- `id`: Auto-incrementing primary key
- `artifact_id`: References parent artifact
- `version`: Version number (1, 2, 3, ...)
- `content`: Full content (HTML, Markdown, or JSON)
- `message_id`: Optional link to chat message that created this version
- `created_at`: When this version was created

**Notes:**
- ON DELETE CASCADE: Deleting artifact deletes all versions
- ON DELETE SET NULL: Deleting message doesn't delete artifact/version
- UNIQUE(artifact_id, version): Prevents duplicate versions

## SQLAlchemy Models

Add to `src/dash/db.py`:

```python
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    visibility: Mapped[str] = mapped_column(Text, default="organization")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        Text, ForeignKey("artifacts.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

## Store Methods

Add to `Store` class in `src/dash/db.py`:

```python
async def create_artifact(
    self,
    artifact_id: str,
    title: str,
    type: str,
    content: str,
    conversation_id: uuid.UUID | None = None,
    message_id: int | None = None,
) -> Artifact:
    artifact = Artifact(
        id=artifact_id,
        conversation_id=conversation_id,
        title=title,
        type=type,
        current_version=1,
    )
    version = ArtifactVersion(
        artifact_id=artifact_id,
        version=1,
        content=content,
        message_id=message_id,
    )
    async with self._session() as session, session.begin():
        session.add(artifact)
        session.add(version)
    return artifact


async def add_artifact_version(
    self, artifact_id: str, content: str, message_id: int | None = None
) -> int:
    async with self._session() as session, session.begin():
        artifact = await session.get(Artifact, artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact {artifact_id} not found")
        
        new_version = artifact.current_version + 1
        version = ArtifactVersion(
            artifact_id=artifact_id,
            version=new_version,
            content=content,
            message_id=message_id,
        )
        artifact.current_version = new_version
        artifact.updated_at = func.now()
        session.add(version)
    return new_version


async def get_artifact(
    self, artifact_id: str, version: int | None = None
) -> tuple[Artifact, ArtifactVersion] | None:
    async with self._session() as session:
        artifact = await session.get(Artifact, artifact_id)
        if artifact is None:
            return None
        
        version_num = version if version is not None else artifact.current_version
        result = await session.execute(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == artifact_id,
                ArtifactVersion.version == version_num,
            )
        )
        artifact_version = result.scalar_one_or_none()
        if artifact_version is None:
            return None
        
        return (artifact, artifact_version)


async def list_artifacts(
    self, conversation_id: uuid.UUID | None = None, limit: int = 100
) -> Sequence[Artifact]:
    async with self._session() as session:
        stmt = select(Artifact).order_by(Artifact.created_at.desc()).limit(limit)
        if conversation_id is not None:
            stmt = stmt.where(Artifact.conversation_id == conversation_id)
        rows = await session.scalars(stmt)
        return rows.all()
```

## Migration

Create `src/dash/migrations/versions/0006_artifacts.py`:

```python
"""artifacts

Revision ID: 0006
Revises: 0005
Create Date: 2024-XX-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'

def upgrade() -> None:
    op.create_table(
        'artifacts',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('current_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('visibility', sa.Text(), nullable=False, server_default='organization'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_artifacts_conversation', 'artifacts', ['conversation_id'])
    op.create_index('idx_artifacts_created_at', 'artifacts', [sa.text('created_at DESC')])

    op.create_table(
        'artifact_versions',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('artifact_id', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('artifact_id', 'version')
    )
    op.create_index('idx_artifact_versions_artifact', 'artifact_versions', ['artifact_id', sa.text('version DESC')])

def downgrade() -> None:
    op.drop_index('idx_artifact_versions_artifact', 'artifact_versions')
    op.drop_table('artifact_versions')
    op.drop_index('idx_artifacts_created_at', 'artifacts')
    op.drop_index('idx_artifacts_conversation', 'artifacts')
    op.drop_table('artifacts')
```

## Testing

```python
# tests/test_artifacts_db.py

async def test_create_artifact(store):
    artifact = await store.create_artifact(
        artifact_id="test-abc123",
        title="Test Proposal",
        type="markdown",
        content="# Test\n\nContent here",
        conversation_id=some_uuid,
        message_id=42
    )
    assert artifact.id == "test-abc123"
    assert artifact.current_version == 1
    
async def test_add_version(store):
    # ... create artifact ...
    version = await store.add_artifact_version(
        artifact_id="test-abc123",
        content="# Updated\n\nNew content",
        message_id=43
    )
    assert version == 2
    
    result = await store.get_artifact("test-abc123")
    assert result is not None
    artifact, latest_version = result
    assert artifact.current_version == 2
    assert latest_version.content == "# Updated\n\nNew content"
```
