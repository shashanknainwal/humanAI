from types import SimpleNamespace


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(name, input, id="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=input, id=id)


def response(*blocks, stop_reason=None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeClaude:
    """Returns scripted responses and records every request."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._responses.pop(0)


class FakeMeeting:
    def __init__(self, utterance_batches=()):
        self.batches = [list(b) for b in utterance_batches]
        self.spoken, self.chat, self.statuses = [], [], []
        self.joined = self.left = None

    async def join(self, url, name):
        self.joined = (url, name)

    async def leave(self):
        self.left = True

    async def speak(self, text):
        self.spoken.append(text)

    async def post_chat(self, message):
        self.chat.append(message)

    async def snapshot(self):
        return "aW1n", "image/png"

    async def set_status(self, animation):
        self.statuses.append(animation)

    async def new_utterances(self):
        return self.batches.pop(0) if self.batches else []


def seg(text, speaker="Sam", start=0.0):
    return {"text": text, "speaker": speaker, "start": start, "end": start + 1}
