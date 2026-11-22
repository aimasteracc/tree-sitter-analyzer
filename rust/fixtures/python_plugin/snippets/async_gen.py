"""异步生成器与 yield 形态。"""


async def counter(start: int, stop: int):
    """异步生成器:依次产出 [start, stop) 的整数。"""
    current = start
    while current < stop:
        yield current
        current += 1


async def relay(source):
    """转发另一个异步迭代器产出的值。"""
    async for item in source:
        yield item


def numbers():
    """普通生成器:使用 yield from 委托。"""
    yield from range(3)


class AsyncPipeline:
    """消费异步生成器的管道。"""

    async def collect(self, source):
        """把异步生成器的产出收集为列表。"""
        results = []
        async for value in source:
            results.append(value)
        return results


async def main() -> None:
    """驱动上述异步生成器。"""
    pipeline = AsyncPipeline()
    doubled = [n async for n in counter(0, 5)]
    await pipeline.collect(counter(0, 3))
    return doubled
