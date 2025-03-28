import asyncio
from datetime import datetime
from enum import StrEnum
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel
from result import Result, is_err
from sqlmodel import Field, Session, SQLModel, create_engine, select

from src.generate import (
    generate_and_save_chat,
    generate_and_save_draft,
    generate_and_save_summary,
)

from .mail_db import MailDB


class JOB_TYPE(StrEnum):
    summary = "summary"
    draft = "draft"
    chat = "chat"


class STATUS(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


JOB_FUNCS = job_funcs = {
    JOB_TYPE.summary: generate_and_save_summary,
    JOB_TYPE.chat: generate_and_save_chat,
    JOB_TYPE.draft: generate_and_save_draft,
}


class JobStatusSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_type: str
    email_message_id: str = Field(index=True)
    account_id: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    output: Optional[str] = None

    @classmethod
    def from_job_status(cls, status: "JobStatus") -> "JobStatusSQL":
        return cls(
            job_type=str(status.job_type),
            email_message_id=status.email_message_id,
            account_id=status.account_id,
            status=str(status.status),
            start_time=status.start_time,
            end_time=status.end_time,
            error_message=status.error_message,
            output=status.output,
        )


class JobStatus(BaseModel):
    job_type: JOB_TYPE
    email_message_id: str
    account_id: str
    status: STATUS
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    output: Optional[str] = None

    @classmethod
    def from_sql_model(cls, status: "JobStatusSQL") -> "JobStatus":
        return cls(
            job_type=status.job_type,
            email_message_id=str(status.email_message_id),
            account_id=status.account_id,
            status=status.status,
            start_time=status.start_time,
            end_time=status.end_time,
            error_message=status.error_message,
            output=status.output,
        )


class BackgroundTaskManager:
    def __init__(self, dbs: dict[str, MailDB], base_dir: str = "db/status.sql"):
        self.dbs = dbs
        self.engine = create_engine(f"sqlite:///{base_dir}/status.sql", echo=False)
        SQLModel.metadata.create_all(self.engine)

    def query_status(self, *where_clauses) -> List[JobStatus]:
        """Allows to any kind of query of the status"""
        with Session(self.engine) as session:
            statement = select(JobStatusSQL)
            for clause in where_clauses:
                statement = statement.where(clause)
            statuses = session.exec(statement).all()
        return [JobStatus.from_sql_model(status=status) for status in statuses]

    def add_job(
        self, job_type: JOB_TYPE, email_message_id: str, account_id: str
    ) -> JobStatusSQL:
        if account_id not in self.dbs:
            raise ValueError("invalid account_od")

        """Simply adds new job to sql"""
        job = JobStatusSQL(
            job_type=job_type,
            email_message_id=email_message_id,
            status=STATUS.pending,
            account_id=account_id,
        )

        with Session(self.engine) as session:
            session.add(job)
            session.commit()
            session.refresh(job)

        logger.debug(f"Added job ({job_type}) for email {email_message_id}")
        return job

    async def update_job(self, job: JobStatusSQL) -> None:
        with Session(self.engine) as session:
            session.merge(job)
            session.commit()
        logger.debug(f"Updated job {job.id} to status '{job.status}'")

    async def run_job(self, job: JobStatusSQL) -> None:
        # Mark as in_progress and update start_time
        job.status = STATUS.in_progress
        job.start_time = datetime.now()
        await self.update_job(job)

        result: Result = await asyncio.to_thread(
            JOB_FUNCS[job.job_type],
            self.dbs[job.account_id],
            job.email_message_id,
        )

        if is_err(result):
            logger.exception(f"Job {job.id} failed: {result.err()}")
            job.error_message = str(result.err())
            job.status = STATUS.failed
        else:
            logger.success(f"Job {job.id} succeded")
            job.status = STATUS.completed

        job.end_time = datetime.now()
        await self.update_job(job)

    async def process_pending_jobs(self, job_type: JOB_TYPE) -> None:
        with Session(self.engine) as session:
            stmt = select(JobStatusSQL).where(
                JobStatusSQL.job_type == job_type,
                JobStatusSQL.status == STATUS.pending,
            )
            pending_jobs = session.exec(stmt).all()

        if pending_jobs:
            logger.info(f"Processing {len(pending_jobs)} pending '{job_type}' jobs.")

        for job in pending_jobs:
            await self.run_job(job)

    async def run(self):
        logger.info("Start Async Loop")

        while True:
            await self.process_pending_jobs(
                JOB_TYPE.chat
            )  # ignore the palcehodel func here!
            await self.process_pending_jobs(
                JOB_TYPE.summary
            )  # ignore the palcehodel func here!
            # await self.process_pending_jobs(JOB_TYPE.draft, self.generate_summary_job)
            await asyncio.sleep(5)
