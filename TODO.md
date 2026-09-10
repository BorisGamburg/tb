# TODO

## Partial OPEN

- [ ] **3. REARM после partial OPEN**
  - Проверить фактическую цепочку `GridMTFStrategy → _execute_open() → _resolve_rearm()`.
  - Определить, правильно ли, что partial OPEN имеет `executed=True` и поэтому считается завершённым действием.
  - Убедиться, что после partial OPEN не возникает ошибочного повторного REARM или, наоборот, не пропускается требуемый REARM.
