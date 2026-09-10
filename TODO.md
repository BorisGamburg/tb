# TODO

## Partial OPEN

## CLOSE execution handling

### Normal execution

The collapse algorithm calculates a price band for closing two levels.

Normal execution requires both conditions:

- the CLOSE order is filled completely;
- the actual execution price is inside the calculated price band.

In this case, perform the normal collapse of the two levels.

### Non-normal execution

If the order is not filled completely or the execution price is outside the price band, do not split levels into arbitrary partial quantities.

For any non-normal execution:

1. Take the actual execution price.
2. Find the nearest level below the execution price.
3. If such a level exists, close that level completely.
4. If there is no level below the execution price, close the nearest level above it completely.

This same rule applies to partial fills and to full fills outside the price band.

The goal is to preserve whole levels and avoid creating fragmented levels. Partial execution is expected to be rare; the actual filled quantity is not distributed between levels.
