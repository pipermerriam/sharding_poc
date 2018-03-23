import asyncio
import logging
import random
import time

from messages import (
    ProposalMessage,
)
from smc import (
    SMC,
)


PERIOD_TIME = 75.


async def collator(network, shard_id, address, smc):
    if address not in smc.collator_pool:
        raise ValueError("Collator pool in SMC does not contain the given address")
    collation_coros_and_periods = []  # [(coroutine, period), ...]

    last_period = None
    while True:
        # wait for next period
        while smc.period == last_period:
            asyncio.sleep(PERIOD_TIME / 2)
        last_period = smc.period

        # remove finished coroutines
        collation_coros_and_periods = [
            (coro, period)
            for coro, period
            in collation_coros_and_periods
            if not coro.done()
        ]

        # when a new period starts, check if we're eligible for some shard and if so start to
        # collate
        for period in smc.get_eligible_periods(shard_id, address):
            if period in [p for _, p in collation_coros_and_periods]:
                continue  # collation coro already running

            coro = collate(network, shard_id, period, address, smc)
            collation_coros_and_periods.append((coro, period))


async def collate(network, shard_id, period, address, smc):
    while smc.period < period:
        asyncio.sleep(PERIOD_TIME / 5)

    # overslept
    if smc.period != period:
        return

    end_time = time.time() + PERIOD_TIME / 2

    message_queue = asyncio.Queue()
    network.outputs.append(message_queue)
    proposals = await collect_proposals(network, shard_id, period, message_queue, end_time)
    network.outputs.remove(message_queue)

    smc.submit_proposal(random.choice(proposals))


async def collect_proposals(shard_id, period, message_queue, end_time):
    proposals = []
    while True:
        try:
            coro = collect_proposal(shard_id, period, message_queue)
            proposal = await asyncio.wait_for(coro, timeout=end_time - time.time())
            proposals.append(proposal)
        except TimeoutError:
            return proposals


async def collect_proposal(shard_id, period, message_queue):
    while True:
        message = await message_queue.get()
        if isinstance(message, ProposalMessage):
            proposal = message.proposal
            if proposal.shard_id == shard_id and proposal.period == period:
                return proposal
