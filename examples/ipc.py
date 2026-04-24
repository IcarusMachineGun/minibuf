import enum
import multiprocessing as mp
import random
import string
from multiprocessing.connection import Connection
from typing import Self

# import logging
# logging.getLogger("minibuf").setLevel("DEBUG")
from minibuf import *


class MsgType(enum.IntEnum):
    Auth = enum.auto()
    Payload = enum.auto()
    LargeMsg = enum.auto()


class Envelope(BaseMessage):
    type: MsgType = field(1)
    payload: bytes = field(2)


class Auth(BaseMessage):
    login: str = field(1)
    password: str = field(2)

    @classmethod
    def generate(cls) -> Self:
        loging = ''.join(random.choices(string.ascii_letters, k=random.randrange(8, 31)))
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randrange(16, 63)))
        return cls(loging, password)


class Payload(BaseMessage):
    text: str = field(1)
    blob: bytes = field(2)
    numbers: list[int32] = field(3)

    @classmethod
    def generate(cls) -> Self:
        rnd = [random.random() for _ in range(3)]
        total = sum(rnd)
        perc = [(r / total) * 3 for r in rnd]
        size_bytes = random.randint(500, 1999)
        text = ''.join(random.choices(string.ascii_letters, k=int(perc[0] * size_bytes)))
        blob = random.randbytes(int(perc[1] * size_bytes))
        num = [random.randint(-(2**31), 2**31 - 1) for _ in range(int(perc[2] * size_bytes) // 4)]
        return cls(text, blob, num) # type: ignore


class LargeMsg(BaseMessage):
    blob: bytes = field(1)
    text: str = field(2)

    @classmethod
    def generate(cls) -> Self:
        size_bytes = random.randint(2000, 1000000)
        rnd = [random.random() for _ in range(2)]
        total = sum(rnd)
        blob_p, text_p = [(r / total) * 2 for r in rnd]
        blob = random.randbytes(int(blob_p * size_bytes))
        text = ''.join(random.choices(string.ascii_letters, k=int(text_p * size_bytes)))
        return cls(blob, text)


type_to_msg: dict[MsgType, Auth | Payload | LargeMsg] = {MsgType[cls.__name__]: cls for cls in [Auth, Payload, LargeMsg]}


def send(conn: Connection, msgs: list[Auth | Payload | LargeMsg]):
    for msg in msgs:
        envl = Envelope(MsgType[msg.__class__.__name__], msg.to_bytes())
        conn.send_bytes(envl.to_bytes())
    conn.close()


def recv(conn: Connection):
    try:
        while True:
            envlp = Envelope.from_bytes(conn.recv_bytes())
            msg = type_to_msg[envlp.type].from_bytes(envlp.payload)
            print(f'Received message {envlp.type!r}')
    except EOFError:
        print('Connection closed by sender')


if __name__ == '__main__':
    print('Generating data...')
    msgs = [Auth.generate() for _ in range(100)] + [Payload.generate() for _ in range(50)] + [LargeMsg.generate() for _ in range(10)]

    random.shuffle(msgs)
    print(f'Generated {len(msgs)} messages.')

    conn1, conn2 = mp.Pipe(duplex=False)

    p1 = mp.Process(target=recv, args=(conn1,))
    p2 = mp.Process(target=send, args=(conn2, msgs))

    p1.start()
    p2.start()
    conn2.close()

    p1.join()
    p2.join()