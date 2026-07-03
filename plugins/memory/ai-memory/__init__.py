from provider import AiMemoryProvider


def register(ctx: object) -> type[AiMemoryProvider]:
    return AiMemoryProvider
