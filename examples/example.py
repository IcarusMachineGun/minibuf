import enum
import json

from minibuf import *


class Address(BaseMessage):
    street: str = field(1)
    postal_code: str | None = field(3, default=None)
    apartment: str | None = field(4, default=None)
    city: str = field(2, default='Unknown City')


class Product(BaseMessage):
    id: uint64 = field(1)
    name: str = field(2)
    price: double = field(3, default=0.0)
    in_stock: bool = field(4, default=False)
    category_id: uint32 = field(5, default=0)


class Order(BaseMessage):
    class LineItem(BaseMessage):
        product_id: uint64 = field(1)
        unit_price: double = field(3)
        discount: float | None = field(4, default=None)
        quantity: uint32 = field(2, default=1)

    class Status(enum.IntEnum):
        PENDING = 0
        PROCESSING = 1
        SHIPPED = 2
        DELIVERED = 3
        CANCELLED = 4

    order_id: uint64 = field(1)
    customer_id: uint64 = field(2)

    items: list[LineItem] = field(7)

    shipping_address: Address = field(8)
    metadata: dict[str, str] = field(10)

    promo_code: str | None = field(3, default=None)
    notes: str | None = field(4, default=None)

    billing_address: Address | None = field(9, default=None)
    status: Status = field(5, default=0)
    created_at: uint64 = field(6, default=0)



class UserRole(enum.IntEnum):
    UNKNOWN = 0
    ADMIN = 1
    USER = 2
    GUEST = 3
    MODERATOR = 4


class UserProfile(BaseMessage):
    class Settings(BaseMessage):

        class Privacy(BaseMessage):
            profile_public: bool = field(1, default=True)
            show_email: bool = field(2, default=False)
            last_seen_visible: bool = field(3, default=True)

        privacy: Privacy = field(4)
        email_notifications: bool = field(1, default=True)
        push_notifications: bool = field(2, default=True)
        theme: str = field(3, default='light')

    user_id: uint64 = field(1)
    username: str = field(2)
    settings: Settings = field(5)
    recent_orders: list[uint64] | None = field(6, default=None)
    role: UserRole | None = field(3, default=None)
    status: UserRole = field(4, default_factory=lambda: UserRole.USER)


inputs: dict[str, type[Address | Order | UserProfile]] = {
    'address_test': Address,
    'order_minimal': Order,
    'order_full': Order,
    'user_profile_minimal': UserProfile,
    'user_profile': UserProfile,
}


with open('examples/fake_inputs.json', encoding='utf-8') as f:
    data = json.load(f)

for key, cls in inputs.items():
    cls.to_proto3(f'examples/generated_proto/{cls.__name__}.proto')

    input_ = data[key]

    msg = cls.from_dict(input_)
    msg2 = cls.from_bytes(msg.to_bytes())

    output = msg2.to_dict()
    with open(f'examples/outputs/{key}.json', 'w') as f:
        json.dump(output, f, indent=4)
