"""Bounded handoff: keep latest UI states, preserve ordered durable events."""
from collections import OrderedDict
from queue import Empty
from threading import Condition


class CaptureEvents:
    STATES={'counts','diagnostics','inventory','inventory_snapshot'}

    def __init__(self,limit=128):
        self.limit=limit;self.items=OrderedDict();self.condition=Condition()

    def put(self,item):
        token,kind,_=item
        key=(token,kind) if kind in self.STATES else object()
        with self.condition:
            # Replacement moves to the end, retaining event ordering by update.
            if key in self.items:del self.items[key]
            while len(self.items)>=self.limit:self.condition.wait()
            self.items[key]=item;self.condition.notify_all()

    def get_nowait(self):
        with self.condition:
            if not self.items:raise Empty
            _,item=self.items.popitem(last=False);self.condition.notify_all();return item

    def empty(self):
        with self.condition:return not self.items

    def qsize(self):
        with self.condition:return len(self.items)
