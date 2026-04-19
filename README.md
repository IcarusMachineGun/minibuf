# minibuf

Toy protocol buffers implementation on python (and for python) without dependencies.

_Inspired by Google's Protocol Buffers ([github](https://github.com/protocolbuffers/protobuf))_ \
[credits](CREDITS)

Using LEB128 for variable length integer encoding

features:

* Protobuf wire‑compatible (using output of `to_proto3` yields identical serialization)


### Notes

No full runtime type checking. Only limited validation:

* Field number duplicates/overflow
* Integer overflow
* Type annotation validation for `Mapping`, `list`/`tuple` and `Union`
* Map type validation when translating to proto3
* Missing required argument
* Both `default` and `default_factory` are provided (mutually exclusive)
* Unsupported type