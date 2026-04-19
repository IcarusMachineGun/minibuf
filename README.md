# minibuf

Toy protocol buffers implementation on python (and for python) without dependencies.

_Inspired by Google's Protocol Buffers ([github](https://github.com/protocolbuffers/protobuf))_ \
[credits](CREDITS)

Using LEB128 for variable length integer encoding

### Disclaimer

**DO NOT USE IN PRODUCTION.** This project only for recreational and learning purposes only. 

### Features:

* Protobuf wire‑compatible (using output of `to_proto3` yields identical serialization)

### Limitations

No full runtime type checking. Only limited validation:

* Field number duplicates/overflow
* Integer overflow
* Type annotation validation for `Mapping`, `list`/`tuple` and `Union`
* Map type validation when translating to proto3
* Missing required argument
* Both `default` and `default_factory` are provided (mutually exclusive)
* Unsupported type

### Installation
```bash
pip install git+https://github.com/IcarusMachineGun/minibuf.git
```

### Usage
```python
>>> import enum
>>> from minibuf import *
>>> class PhoneNumber(BaseMessage):
...     class PhoneType(enum.IntEnum):
...         MOBILE = enum.auto()
...         HOME = enum.auto()
...         WORK = enum.auto()
... 
...     number: str = field(1)
...     type: PhoneType = field(2)
...
... class Person(BaseMessage):
...     name: str = field(1)
...     id: int32 = field(2)
...     email: str = field(3)
... 
...     phones: list[PhoneNumber] = field(4, is_repeated=True)
>>> person1 = Person('Alex', 123, 'alexalex2007@email', [PhoneNumber('+12345678', PhoneNumber.PhoneType.MOBILE)])
>>> e = person1.encode()
>>> Person.from_bytes(e.bytes).pretty()
```
```text
{'email': 'alexalex2007@email',
 'id': 123,
 'name': 'Alex',
 'phones': [{'number': '+12345678', 'type': 'MOBILE'}]}
```
```python
>>> Person.to_proto3()
```
```text
syntax = "proto3";

message PhoneNumber {
  enum PhoneType {
    MOBILE = 1;
    HOME = 2;
    WORK = 3;
  }
  string number = 1;
  PhoneType type = 2;
}
message Person {
  string name = 1;
  int32 id = 2;
  string email = 3;
  repeated PhoneNumber phones = 4;
}
```

### TODO:
- [ ] tests
- [ ] fix some type checker issues
