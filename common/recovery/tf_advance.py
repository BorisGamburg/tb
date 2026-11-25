def advance_entry_tf(state_store, app_ctx) -> None:
    """Переходит на следующий таймфрейм входа и сохраняет состояние.

    Вызывается после успешного открытия уровня, который должен сдвинуть
    таймфрейм. На последнем таймфрейме списка ничего не меняется.
    """
    data = state_store.data

    current_tf = data.entry_tf

    # Последний таймфрейм в списке -> остаёмся на нём
    if not data.advance_tf():
        return

    state_store.save()

    app_ctx.logger.info(
        f"Entry TF advanced: entry_tf changed "
        f"from {current_tf} to {data.entry_tf}"
    )
