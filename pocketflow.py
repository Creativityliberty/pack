import asyncio
import warnings
import copy
import time

class BaseNode:
    def __init__(self):
        self.params = {}
        self.successors = {}
    
    def set_params(self, params):
        self.params = params
        
    def next(self, node, action="default"):
        if action in self.successors:
            warnings.warn(f"Overwriting successor for action '{action}'")
        self.successors[action] = node
        return node
        
    def prep(self, shared):
        return None
        
    def exec(self, prep_res):
        return None
        
    def post(self, shared, prep_res, exec_res):
        return "default"
        
    def _exec(self, prep_res):
        return self.exec(prep_res)
        
    def _run(self, shared):
        p = self.prep(shared)
        e = self._exec(p)
        return self.post(shared, p, e)
        
    def run(self, shared):
        if self.successors:
            warnings.warn("Node won't run successors. Use Flow.")
        return self._run(shared)
        
    def __rshift__(self, other):
        return self.next(other)
        
    def __sub__(self, action):
        if isinstance(action, str):
            return _ConditionalTransition(self, action)
        raise TypeError("Action must be a string")

class _ConditionalTransition:
    def __init__(self, src, action):
        self.src = src
        self.action = action
        
    def __rshift__(self, tgt):
        return self.src.next(tgt, self.action)

class Node(BaseNode):
    def __init__(self, max_retries=1, wait=0):
        super().__init__()
        self.max_retries = max_retries
        self.wait = wait
        
    def exec_fallback(self, prep_res, exc):
        raise exc
        
    def _exec(self, prep_res):
        for self.cur_retry in range(self.max_retries):
            try:
                return self.exec(prep_res)
            except Exception as e:
                if self.cur_retry == self.max_retries - 1:
                    return self.exec_fallback(prep_res, e)
                if self.wait > 0:
                    time.sleep(self.wait)

class Flow(BaseNode):
    def __init__(self, start=None):
        super().__init__()
        self.start_node = start
        
    def start(self, start):
        self.start_node = start
        return start
        
    def get_next_node(self, curr, action):
        return curr.successors.get(action or "default")
        
    def _orch(self, shared, params=None):
        curr = copy.copy(self.start_node)
        p = params or {**self.params}
        last_action = None
        while curr:
            curr.set_params(p)
            last_action = curr._run(shared)
            curr = copy.copy(self.get_next_node(curr, last_action))
        return last_action
        
    def _run(self, shared):
        return self._orch(shared)

class BatchNode(Node):
    def _exec(self, items):
        return [super(BatchNode, self)._exec(i) for i in (items or [])]

class BatchFlow(Flow):
    def _run(self, shared):
        pr = self.prep(shared) or []
        for bp in pr:
            self._orch(shared, {**self.params, **bp})
        return self.post(shared, pr, None)

class AsyncNode(BaseNode):
    def __init__(self, max_retries=1, wait=0):
        super().__init__()
        self.max_retries = max_retries
        self.wait = wait
        
    async def prep_async(self, shared):
        return self.prep(shared)
        
    async def exec_async(self, prep_res):
        return self.exec(prep_res)
        
    async def post_async(self, shared, prep_res, exec_res):
        return self.post(shared, prep_res, exec_res)
        
    async def exec_fallback_async(self, prep_res, exc):
        raise exc
        
    async def _exec_async(self, prep_res):
        for self.cur_retry in range(self.max_retries):
            try:
                res = self.exec_async(prep_res)
                if asyncio.iscoroutine(res):
                    return await res
                return res
            except Exception as e:
                if self.cur_retry == self.max_retries - 1:
                    fallback_res = self.exec_fallback_async(prep_res, e)
                    if asyncio.iscoroutine(fallback_res):
                        return await fallback_res
                    return fallback_res
                if self.wait > 0:
                    await asyncio.sleep(self.wait)
                    
    async def _run_async(self, shared):
        p = self.prep_async(shared)
        if asyncio.iscoroutine(p):
            p = await p
        e = await self._exec_async(p)
        post_res = self.post_async(shared, p, e)
        if asyncio.iscoroutine(post_res):
            post_res = await post_res
        return post_res

class AsyncFlow(Flow):
    async def _orch_async(self, shared, params=None):
        curr = copy.copy(self.start_node)
        p = params or {**self.params}
        last_action = None
        while curr:
            curr.set_params(p)
            if isinstance(curr, AsyncNode):
                last_action = await curr._run_async(shared)
            else:
                last_action = curr._run(shared)
            nxt = self.get_next_node(curr, last_action)
            curr = copy.copy(nxt)
        return last_action
        
    async def _run_async(self, shared):
        return await self._orch_async(shared)
        
    def _run(self, shared):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(self._run_async(shared), loop).result()
        else:
            return loop.run_until_complete(self._run_async(shared))
