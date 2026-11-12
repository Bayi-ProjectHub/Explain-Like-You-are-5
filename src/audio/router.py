"""音频转写的 HTTP 接口。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from .schemas import TaskResponse
from .service import (
    AudioTooLargeError,
    TaskNotFoundError,
    TranscriptionService,
    UnsupportedAudioFormatError,
)

router = APIRouter(prefix="/audio", tags=["audio"])


def _service(request: Request) -> TranscriptionService:
    return request.app.state.transcription_service


@router.post("/transcriptions", status_code=202, response_model=TaskResponse)
async def create_transcription(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="音频文件"),
    language: str | None = Form(None, description="ISO 语言代码，如 zh、en；不传则自动识别"),
) -> TaskResponse:
    """上传音频，返回任务 id；转写在后台进行，通过 GET 接口轮询结果。"""
    service = _service(request)
    try:
        task = await service.submit(file, language=language)
    except UnsupportedAudioFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except AudioTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    # 转写是 CPU 密集的同步操作，放进线程执行，避免阻塞事件循环
    background_tasks.add_task(asyncio.to_thread, service.process, task.task_id, language)
    return task


@router.get("/transcriptions/{task_id}", response_model=TaskResponse)
async def get_transcription(request: Request, task_id: str) -> TaskResponse:
    """查询任务状态；status 为 completed 时 result 有值，failed 时 error 有值。"""
    try:
        return _service(request).get(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
