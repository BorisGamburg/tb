def advance_entry_tf(state_store, app_ctx) -> None:
    """Переходит на следующую ступень таймфреймов и сохраняет состояние.

    Вызывается после успешного открытия уровня. На последней ступени
    ничего не меняется. Что именно сдвигается, решает data.advance_tf().
    """
    if not state_store.data.advance_tf():
        return

    state_store.save()

    app_ctx.logger.info("Timeframe step advanced")
