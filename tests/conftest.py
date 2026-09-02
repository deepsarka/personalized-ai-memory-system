import pytest
import pytest_asyncio
from graph.writer import close_driver, init_constraints, init_vector_index


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_neo4j_database():
    await init_constraints()
    await init_vector_index()
    yield
    await close_driver()
