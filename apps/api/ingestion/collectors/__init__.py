from apps.api.ingestion.collectors.base import BaseCollector
from apps.api.ingestion.collectors.chat_imports import FeishuCollector, WechatCollector
from apps.api.ingestion.collectors.deepseek_archive import DeepSeekArchiveCollector
from apps.api.ingestion.collectors.markdown import MarkdownCollector
from apps.api.ingestion.collectors.personal_imports import (
    DiaryCollector,
    EmailCollector,
    VoiceCollector,
)
from apps.api.ingestion.schemas import SourceType

_COLLECTORS: dict[SourceType, type[BaseCollector]] = {
    SourceType.MARKDOWN: MarkdownCollector,
    SourceType.TEXT: MarkdownCollector,
    SourceType.DEEPSEEK_ARCHIVE: DeepSeekArchiveCollector,
    SourceType.WECHAT: WechatCollector,
    SourceType.FEISHU: FeishuCollector,
    SourceType.EMAIL: EmailCollector,
    SourceType.VOICE: VoiceCollector,
    SourceType.DIARY: DiaryCollector,
}


def collector_for(source_type: SourceType) -> BaseCollector:
    return _COLLECTORS[source_type]()


__all__ = [
    "BaseCollector",
    "DeepSeekArchiveCollector",
    "DiaryCollector",
    "EmailCollector",
    "FeishuCollector",
    "MarkdownCollector",
    "VoiceCollector",
    "WechatCollector",
    "collector_for",
]
