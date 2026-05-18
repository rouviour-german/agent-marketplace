import asyncio
import time
import pytest
from agent_mesh.models import AgentBase

class FlakyAgent(AgentBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.should_fail = False

    async def run(self, input: str) -> str:
        if self.should_fail:
            raise RuntimeError("Simulated agent failure")
        return f"OK: {input}"

@pytest.mark.asyncio
async def test_circuit_breaker_tripping():
    agent = FlakyAgent()
    agent._max_failures = 2
    agent._reset_timeout = 0.5 # Fast reset for testing

    # First success
    assert await agent.execute("test") == "OK: test"
    assert agent._circuit_state == "CLOSED"

    # Trip the circuit
    agent.should_fail = True
    with pytest.raises(RuntimeError):
        await agent.execute("fail 1")
    
    assert agent._circuit_state == "CLOSED" # Still closed after 1 failure

    with pytest.raises(RuntimeError):
        await agent.execute("fail 2")
    
    assert agent._circuit_state == "OPEN"

    # Subsequent call fails immediately due to OPEN circuit
    with pytest.raises(RuntimeError, match="Cooling down"):
        await agent.execute("too soon")

@pytest.mark.asyncio
async def test_circuit_breaker_recovery():
    agent = FlakyAgent()
    agent._max_failures = 1
    agent._reset_timeout = 0.1
    
    agent.should_fail = True
    with pytest.raises(RuntimeError):
        await agent.execute("trip")
    assert agent._circuit_state == "OPEN"

    # Wait for reset timeout
    await asyncio.sleep(0.2)
    
    # Next call should be HALF-OPEN and succeed
    agent.should_fail = False
    assert await agent.execute("recover") == "OK: recover"
    assert agent._circuit_state == "CLOSED"

@pytest.mark.asyncio
async def test_bulkhead_isolation():
    class SlowAgent(AgentBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.active_count = 0

        async def run(self, input: str) -> str:
            self.active_count += 1
            await asyncio.sleep(0.2)
            self.active_count -= 1
            return "done"

    agent = SlowAgent(max_concurrent_runs=2)
    
    # Start 3 tasks
    tasks = [
        asyncio.create_task(agent.execute("task 1")),
        asyncio.create_task(agent.execute("task 2")),
        asyncio.create_task(agent.execute("task 3")),
    ]
    
    # Wait a bit
    await asyncio.sleep(0.1)
    
    # Only 2 tasks should be active in 'run' at the same time
    assert agent.active_count == 2
    
    await asyncio.gather(*tasks)
    assert agent.active_count == 0
