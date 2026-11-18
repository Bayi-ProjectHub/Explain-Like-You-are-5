"""词库查询、随机抽题和用户练习的 HTTP 接口。"""

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import TypeAdapter, ValidationError

from ..audio.service import AudioTooLargeError, TaskNotFoundError
from ..config import load_settings
from ..delivery.schemas import PlaybackRange
from .media import MediaError
from .service import PracticeTask
from .vocabulary import Difficulty, Language, draw_term, filter_terms, find_term, load_vocabulary

router = APIRouter(prefix="/practice", tags=["practice"])
presenter_range_array = TypeAdapter(list[PlaybackRange])


@router.get("/vocabulary")
async def vocabulary(category: str | None = None, difficulty: Difficulty | None = None):
    catalog = load_vocabulary()
    settings = load_settings()
    return {
        "version": catalog.version, "categories": catalog.categories,
        "terms": filter_terms(category, difficulty),
        "limits": {"max_upload_mb": settings.max_upload_mb, "max_video_seconds": settings.max_video_seconds},
    }


@router.get("/terms/random")
async def random_term(
    category: str | None = None, difficulty: Difficulty | None = None,
    exclude_id: str | None = Query(None, max_length=100),
):
    term = draw_term(category, difficulty, exclude_id)
    if term is None:
        raise HTTPException(status_code=404, detail="该条件下暂无术语，请换个筛选条件。")
    return term


@router.post("/submissions", status_code=202, response_model=PracticeTask)
async def create_submission(
    request: Request, background_tasks: BackgroundTasks,
    file: UploadFile = File(...), term_id: str = Form(...), language: Language = Form(...),
    presenter_ranges: str = Form("[]", max_length=12000),
):
    term = find_term(term_id)
    if term is None:
        raise HTTPException(status_code=422, detail="术语不存在，请重新抽题。")
    service = request.app.state.practice_service
    try:
        try:
            ranges = sorted(presenter_range_array.validate_json(presenter_ranges), key=lambda item: item.start)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="讲者时段格式不正确。") from exc
        if len(ranges) > 100 or any(b.start < a.end for a, b in zip(ranges, ranges[1:])):
            raise HTTPException(status_code=422, detail="讲者时段不得重叠，最多 100 段。")
        task = await service.submit(file, term, language, ranges)
    except MediaError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except AudioTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    finally:
        await file.close()
    background_tasks.add_task(service.process, task.task_id)
    return task


@router.get("/submissions/{task_id}", response_model=PracticeTask)
async def get_submission(request: Request, task_id: str):
    try:
        return request.app.state.practice_service.get(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="练习任务不存在，服务重启后请重新上传。") from exc
