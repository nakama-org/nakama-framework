# Nakama Framework

A Python framework for building Messenger chatbots, built on FastAPI and SQLAlchemy.

You write handlers, group them into modules, and Nakama takes care of the rest: the Messenger webhook, routing each message to the right handler, multi-step conversations, and saving each user's session in a database.

```bash
pip install nakama-framework
```

Requires Python 3.11+.

## Quick start

```python
import os

from nakama_framework import Button, Context, Module, NakamaApp, run
from nakama_framework.channels.messenger import MessengerChannel, MessengerProfile

greetings = Module("greetings")


@greetings.on_payload("GET_STARTED")
async def get_started(ctx: Context):
    await ctx.send_buttons(
        "Hi! I'm a Nakama bot.",
        [Button(title="Introduce myself", payload="ASK_NAME")],
    )


@greetings.on_payload("ASK_NAME")
async def ask_name(ctx: Context):
    await ctx.ask("What's your name?", "awaiting_name")


@greetings.on_state("awaiting_name")
async def save_name(ctx: Context):
    ctx.session.set("name", ctx.message.text)
    await ctx.reply(f"Nice to meet you, {ctx.message.text}!")


@greetings.on_command("ping")
async def ping(ctx: Context):
    await ctx.reply("pong")


app = NakamaApp()
app.register_channel(
    MessengerChannel(
        page_access_token=os.environ["PAGE_ACCESS_TOKEN"],
        verify_token=os.environ["VERIFY_TOKEN"],
        app_secret=os.environ["APP_SECRET"],
        profile=MessengerProfile(get_started_payload="GET_STARTED"),
    )
)
app.include_module(greetings)


@app.on_fallback
async def fallback(ctx: Context):
    await ctx.reply("Sorry, I didn't get that.")


if __name__ == "__main__":
    run(app)
```

`run(app)` starts a server on port 8000 (or `$PORT`) with:

- `GET /webhook` for Meta's verification handshake
- `POST /webhook` for incoming messages, with the `X-Hub-Signature-256` signature checked against your app secret
- `GET /health` for health checks

Point your Facebook app's webhook to `https://your-domain/webhook` and the bot is live.

## How it works

### Modules and handlers

A `Module` groups related handlers, like a FastAPI router. Each incoming message goes to the first handler that matches, in this order:

| Priority | Decorator | Triggered by |
| --- | --- | --- |
| 1 | `on_payload("ID")`, `on_payload_prefix("NAV_")` | A button or quick reply click |
| 2 | `on_state("name")` | A reply to a question asked with `ctx.ask()` |
| 3 | `on_command("ping")` | A message starting with `/ping` |
| 4 | `on_media(MediaType.IMAGE)` | An image, video, audio, file or location |
| 5 | `on_text(r"regex")` | Free text matching the pattern (captured groups are passed to the handler) |

If nothing matches, the fallback registered with `@app.on_fallback` runs.

Two safety rules keep users from getting stuck. A button click with no handler clears the pending question. A state with no handler is cleared and logged as an error.

### Conversations

`ctx.ask(text, next_state, **data)` sends a question and routes the user's next message to the matching `on_state` handler. Data passed to `ask` is available in that handler as `ctx.state_data`.

The state is cleared automatically after the handler runs, unless the handler sets a new one. That's how you chain a multi-step form:

```python
@orders.on_state("awaiting_quantity")
async def quantity(ctx: Context):
    if not ctx.message.text.isdigit():
        await ctx.ask("Please send a number.", "awaiting_quantity")
        return
    await ctx.ask("Delivery address?", "awaiting_address", quantity=int(ctx.message.text))
```

### Sending messages

Handlers talk to the user through the `Context`:

- `ctx.reply(text)`
- `ctx.send_buttons(text, buttons)`
- `ctx.send_quick_replies(text, buttons)`
- `ctx.send_carousel(items)`
- `ctx.send_image(url_or_path)`
- `ctx.send_file(data, filename)`

For long lists, `Paginator` splits items into pages with "next" and "last" quick replies and keeps its state in the session.

### Sessions and database

Each user has a session (`ctx.session`) with free-form data and the current conversation state. It's loaded before every message and saved after, so it survives restarts.

SQLite (`bot.db`) is used by default. To use another database, pass any async SQLAlchemy URL and install its driver:

```python
app = NakamaApp(database_url="postgresql+asyncpg://user:pass@host/db")
```

You can add your own tables by inheriting from `nakama_framework.database.models.Base`.

### Middleware

A middleware runs before the handler and can stop the message from going further:

```python
from nakama_framework.middleware.base import Middleware, NextFn


class Maintenance(Middleware):
    async def process(self, ctx: Context, next: NextFn) -> None:
        if os.environ.get("MAINTENANCE"):
            await ctx.reply("The bot is under maintenance, come back later.")
            return
        await next()


app.add_middleware(Maintenance())
```

### Messenger profile

`MessengerProfile` declares the Get Started button and the persistent menu. It's sent to Meta every time the bot starts.

```python
from nakama_framework.channels.messenger import MenuItem, MenuItemType

profile = MessengerProfile(
    get_started_payload="GET_STARTED",
    persistent_menu=[
        MenuItem(title="Main menu", payload="MENU"),
        MenuItem(type=MenuItemType.WEB_URL, title="Website", url="https://example.com"),
    ],
)
```

## Testing your bot

`app.handle()` runs the routing without a database or a network call. With no channel registered, replies are only logged, so handlers can be tested directly:

```python
from nakama_framework import Message, NakamaApp, Session, User
from nakama_framework.core import Channel


async def test_ping():
    app = NakamaApp()
    app.include_module(greetings)

    user = User(id="user-1", channel=Channel.MESSENGER)
    result = await app.handle(user, Session(user_id=user.id), Message(text="/ping"))

    assert result.matched
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

Every push to `master` creates a release and publishes it to PyPI. The version is bumped from the commit messages ([Conventional Commits](https://www.conventionalcommits.org/)): `feat:` for a minor version, `fix:` and others for a patch, `!` or `BREAKING CHANGE` for a major one.
