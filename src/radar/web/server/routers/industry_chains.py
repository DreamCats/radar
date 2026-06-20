from __future__ import annotations

from fastapi import APIRouter, HTTPException

from radar.core.industry_chains import IndustryChainNotFoundError
from radar.core.industry_chains import get_industry_chain_detail, list_industry_chains
from radar.web.server.schemas import IndustryChainDetailResponse, IndustryChainListResponse

router = APIRouter(prefix="/api/industry-chains", tags=["industry-chains"])


@router.get("", response_model=IndustryChainListResponse)
def industry_chain_list() -> IndustryChainListResponse:
    return IndustryChainListResponse(**list_industry_chains())


@router.get("/{chain_id}", response_model=IndustryChainDetailResponse)
def industry_chain_detail(chain_id: str) -> IndustryChainDetailResponse:
    try:
        detail = get_industry_chain_detail(chain_id)
    except IndustryChainNotFoundError as exc:
        raise HTTPException(status_code=404, detail="产业链不存在") from exc
    return IndustryChainDetailResponse(
        item=detail.item,
        data=detail.data,
        content_markdown=detail.content_markdown,
    )
