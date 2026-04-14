# Chat API — Flutter Integration Guide

All chat functionality is split across two channels:
- **REST API** — fetch data (conversations list, message history)
- **WebSocket** — real-time events (send messages, typing, delivery/read receipts)

---

## Base URL

```
REST :  https://<host>/api/v1
WS   :  wss://<host>/api/v1
```

> Use `ws://` and `http://` for local development.

---

## Authentication

All REST endpoints require a **Bearer token** in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

The WebSocket uses **first-message auth** (token is never in the URL — URLs appear in server logs in plain text). See the WebSocket section for details.

---

## REST API

All JSON responses use **camelCase** field names.

---

### 1. List Conversations

Returns all conversations for the authenticated user that have at least one message, ordered by most recent message first.

```
GET /chat/conversations
```

**Request headers**
```
Authorization: Bearer <access_token>
```

**Response `200 OK`**
```json
[
  {
    "id": 7,
    "participant1Id": 5,
    "participant2Id": 42,
    "createdAt": "2024-01-15T10:30:00Z",
    "lastMessageAt": "2024-01-15T11:45:00Z"
  },
  {
    "id": 3,
    "participant1Id": 5,
    "participant2Id": 18,
    "createdAt": "2024-01-10T08:00:00Z",
    "lastMessageAt": "2024-01-14T19:22:00Z"
  }
]
```

| Field | Type | Description |
|---|---|---|
| `id` | int | Conversation ID |
| `participant1Id` | int | Always the lower of the two user IDs |
| `participant2Id` | int | Always the higher of the two user IDs |
| `createdAt` | ISO 8601 datetime | When the conversation was created |
| `lastMessageAt` | ISO 8601 datetime | Timestamp of the last message |

Returns an empty array `[]` if the user has no conversations yet.

**Error responses**

| Status | Reason |
|---|---|
| `401 Unauthorized` | Missing or invalid token |
| `503 Service Unavailable` | Database temporarily unavailable |

---

### 2. Get Message History

Fetch paginated messages for a conversation, newest first. Use cursor-based pagination for infinite scroll.

```
GET /chat/conversations/{conversation_id}/messages
```

**Path parameter**

| Parameter | Type | Description |
|---|---|---|
| `conversation_id` | int | ID of the conversation |

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int (1–100) | `50` | Number of messages to return |
| `before_id` | int \| null | — | Cursor — returns messages older than this ID. Omit for the first page. |

**Request headers**
```
Authorization: Bearer <access_token>
```

**Example — first page**
```
GET /chat/conversations/7/messages?limit=50
```

**Example — next page (scroll up)**
```
GET /chat/conversations/7/messages?limit=50&before_id=101
```
Pass the smallest `id` from your current list as `before_id`.

**Response `200 OK`**
```json
[
  {
    "id": 120,
    "conversationId": 7,
    "senderId": 42,
    "content": "Hey, how are you?",
    "messageType": "text",
    "status": "read",
    "createdAt": "2024-01-15T11:45:00Z",
    "deliveredAt": "2024-01-15T11:45:01Z",
    "readAt": "2024-01-15T11:46:00Z"
  },
  {
    "id": 119,
    "conversationId": 7,
    "senderId": 5,
    "content": "All good!",
    "messageType": "text",
    "status": "sent",
    "createdAt": "2024-01-15T11:44:00Z",
    "deliveredAt": null,
    "readAt": null
  }
]
```

| Field | Type | Description |
|---|---|---|
| `id` | int | Message ID |
| `conversationId` | int | Parent conversation |
| `senderId` | int | User ID who sent this message |
| `content` | string | Message text |
| `messageType` | `"text"` \| `"image"` \| `"file"` | Type of message |
| `status` | `"sent"` \| `"delivered"` \| `"read"` | Delivery status |
| `createdAt` | ISO 8601 datetime | When message was sent |
| `deliveredAt` | ISO 8601 datetime \| null | When recipient received it |
| `readAt` | ISO 8601 datetime \| null | When recipient read it |

**Message status lifecycle**
```
sent  →  delivered  →  read
```
- `sent` — saved to DB, recipient has not yet received it
- `delivered` — recipient's device received it (they came online or opened the conversation)
- `read` — recipient sent a `messageRead` event

**Error responses**

| Status | Reason |
|---|---|
| `401 Unauthorized` | Missing or invalid token |
| `404 Not Found` | Conversation does not exist or you are not a participant |
| `503 Service Unavailable` | Database temporarily unavailable |

### 3. Get User Profile

Fetch basic profile info for any active user. Call this when you encounter an unknown `senderId` and cache the result locally — profiles rarely change.

```
GET /users/{user_id}
```

**Request headers**
```
Authorization: Bearer <access_token>
```

**Response `200 OK`**
```json
{
  "id": 42,
  "username": "john_doe",
  "phoneNumber": "+919876543210",
  "profilePictureUrl": "https://example.com/avatar.jpg"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | int | User ID |
| `username` | string \| null | Display name |
| `phoneNumber` | string \| null | E.164 phone number — use to match local contacts |
| `profilePictureUrl` | string \| null | Avatar URL |

**Error responses**

| Status | Reason |
|---|---|
| `401 Unauthorized` | Missing or invalid token |
| `404 Not Found` | User does not exist or is inactive |

---

## WebSocket

All WebSocket JSON fields use **camelCase**.

### Connection URL

```
wss://<host>/api/v1/chat/ws
```

One connection per user session. All conversations are multiplexed over this single connection — **do not open a new connection per conversation**.

---

### Connection Flow

```
Flutter app                          Server
    |                                    |
    |--- TCP + WS Upgrade ----------->  |
    |                                    |  (accepts connection)
    |--- {"type":"auth","token":"..."} ->|  must send within 10 seconds
    |                                    |  (validates JWT, checks user)
    |<-- {"type":"connected", ...} ----|
    |                                    |  connection is now live
    |         [events flow both ways]    |
    |                                    |
    |--- {"type":"pong"} -------------> |  (in reply to server ping)
```

**When to connect:** Right after the user logs in. Keep the connection alive for the entire app session.

**Reconnection:** If the connection drops, reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s). Re-send the auth message immediately after reconnecting.

---

### Step 1 — Connect and Authenticate

After opening the WebSocket, immediately send:

```json
{
  "type": "auth",
  "token": "<access_token>"
}
```

**You must send this within 10 seconds** or the server closes the connection with code `4001`.

On success, the server replies:

```json
{
  "type": "connected",
  "data": {
    "userId": 5
  }
}
```

---

### Client → Server Events

All events after auth follow this envelope:

```json
{
  "type": "<event_type>",
  "data": { ... }
}
```

---

#### `sendMessage` — Send a message

**Case 1 — Existing conversation** (use `conversationId`)

```json
{
  "type": "sendMessage",
  "data": {
    "conversationId": 7,
    "content": "Hello!",
    "messageType": "text"
  }
}
```

**Case 2 — First ever message to a user** (use `targetUserId`)

No prior API call needed. The conversation is created automatically on the server.

```json
{
  "type": "sendMessage",
  "data": {
    "targetUserId": 42,
    "content": "Hey!",
    "messageType": "text"
  }
}
```

The server returns the new `conversationId` in `messageAck`. Store it and use it for all subsequent messages.

| Field | Type | Required | Description |
|---|---|---|---|
| `conversationId` | int | One of these two is required | Use for existing conversations |
| `targetUserId` | int | One of these two is required | Use for the very first message to a user |
| `content` | string (max 4096 chars) | Yes | Message text |
| `messageType` | `"text"` \| `"image"` \| `"file"` | No | Defaults to `"text"` |

---

#### `conversationOpen` — User opened a chat screen

Send this whenever the user navigates into a conversation. The server marks all pending messages as **delivered** and notifies the sender.

```json
{
  "type": "conversationOpen",
  "data": {
    "conversationId": 7
  }
}
```

> Recommended: send this at the same time as calling `GET /chat/conversations/{id}/messages` to load history.

---

#### `typingStart` — User started typing

```json
{
  "type": "typingStart",
  "data": {
    "conversationId": 7
  }
}
```

---

#### `typingStop` — User stopped typing

```json
{
  "type": "typingStop",
  "data": {
    "conversationId": 7
  }
}
```

---

#### `messageRead` — User has read the messages

```json
{
  "type": "messageRead",
  "data": {
    "conversationId": 7
  }
}
```

---

#### `pong` — Heartbeat reply

```json
{
  "type": "pong"
}
```

---

### Server → Client Events

---

#### `connected` — Auth successful

```json
{
  "type": "connected",
  "data": {
    "userId": 5
  }
}
```

---

#### `newMessage` — Incoming message

Lean payload — only message data, no user profile attached.

```json
{
  "type": "newMessage",
  "data": {
    "conversationId": 7,
    "id": 121,
    "senderId": 42,
    "content": "Hey!",
    "messageType": "text",
    "status": "sent",
    "createdAt": "2024-01-15T12:00:00Z"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `conversationId` | int | Conversation this message belongs to |
| `id` | int | Message ID |
| `senderId` | int | User ID of the sender |
| `content` | string | Message text |
| `messageType` | `"text"` \| `"image"` \| `"file"` | Type of message |
| `status` | `"sent"` | Always `"sent"` on arrival |
| `createdAt` | ISO 8601 datetime | When the message was sent |

**How to handle:**
- Look up `conversationId` in your local cache → append the message and update `lastMessageAt`
- If `senderId` is unknown → call `GET /users/{senderId}` once to fetch and cache the profile

---

#### `newConversation` — Brand-new conversation started

Sent to the **recipient only**, and only on the **very first message** of a conversation. Always arrives before `newMessage` in the same sequence. Use it to insert a new row in the inbox before the message arrives.

```json
{
  "type": "newConversation",
  "data": {
    "id": 7,
    "participant1Id": 5,
    "participant2Id": 42,
    "createdAt": "2024-01-15T12:00:00Z",
    "lastMessageAt": "2024-01-15T12:00:00Z",
    "otherUser": {
      "id": 42,
      "username": "john_doe",
      "phoneNumber": "+919876543210",
      "profilePictureUrl": "https://example.com/avatar.jpg"
    }
  }
}
```

| Field | Type | Description |
|---|---|---|
| `id` | int | Conversation ID |
| `participant1Id` | int | Lower of the two user IDs |
| `participant2Id` | int | Higher of the two user IDs |
| `createdAt` | ISO 8601 datetime | When the conversation was created |
| `lastMessageAt` | ISO 8601 datetime | Timestamp of the first message |
| `otherUser.id` | int | Sender's user ID |
| `otherUser.username` | string \| null | Sender's username |
| `otherUser.phoneNumber` | string \| null | Sender's phone in E.164 format — match against local contacts |
| `otherUser.profilePictureUrl` | string \| null | Sender's avatar URL |

**How to handle:**
1. Insert a new conversation row in your local inbox using this payload
2. Cache `otherUser` as the profile for `otherUser.id`
3. The `newMessage` that follows will reference the same `conversationId` — append it normally

---

#### `messageAck` — Your message was saved

Always contains `conversationId` — critical for the first-message case.

```json
{
  "type": "messageAck",
  "data": {
    "conversationId": 7,
    "messageId": 121,
    "status": "sent"
  }
}
```

> **Important:** For first messages (sent with `targetUserId`), store the returned `conversationId` and use it for all future events in this chat.

---

#### `messageDelivered` — Your message was delivered

```json
{
  "type": "messageDelivered",
  "data": {
    "conversationId": 7,
    "messageIds": [119, 120, 121]
  }
}
```

---

#### `messageRead` — Your message was read

```json
{
  "type": "messageRead",
  "data": {
    "conversationId": 7,
    "messageIds": [119, 120, 121]
  }
}
```

---

#### `typing` — Other user typing indicator

```json
{
  "type": "typing",
  "data": {
    "conversationId": 7,
    "userId": 42,
    "isTyping": true
  }
}
```

`isTyping: false` means they stopped typing.

---

#### `ping` — Heartbeat from server

Sent every 30 seconds. Reply immediately with `{"type": "pong"}`.

```json
{
  "type": "ping"
}
```

---

#### `error` — Event-level error

```json
{
  "type": "error",
  "data": {
    "message": "Content cannot be empty."
  }
}
```

| Message | Cause |
|---|---|
| `conversationId or targetUserId is required.` | `sendMessage` sent without either field |
| `Content cannot be empty.` | `sendMessage` with blank content |
| `Message too long (max 4096 chars).` | Content exceeds 4096 characters |
| `Conversation X not found or access denied.` | Invalid `conversationId` or not a participant |
| `Cannot create a conversation with yourself.` | `targetUserId` is your own user ID |
| `Failed to create conversation. Please try again.` | DB error during lazy conversation creation |
| `Failed to send message. Please try again.` | DB error while saving the message |
| `Invalid JSON.` | Malformed JSON frame sent |
| `Unknown event type: 'X'` | Unrecognised event type |

---

### WebSocket Close Codes

| Code | Meaning | What to do |
|---|---|---|
| `4001` | Auth failure (timeout, bad token, user not found) | Show login screen or refresh token |
| `4008` | Heartbeat timeout (no `pong` received in 90s) | Reconnect |
| `1011` | Internal server error | Reconnect with backoff |
| `1000` | Normal closure | No action needed |
| `1001` | Server going away (deploy/restart) | Reconnect with backoff |

---

## Recommended Flutter Implementation

### App startup / login
1. Login via auth API → receive `access_token`
2. Open WebSocket → send `auth` message
3. On `connected` → call `GET /chat/conversations` to load the inbox

### Opening an existing conversation (from inbox)
1. You already have the `conversationId` from the conversations list
2. Call `GET /chat/conversations/{id}/messages` to load history
3. Send `conversationOpen` over WS to trigger delivery receipts
4. Listen for `newMessage` events on the WS to append incoming messages live

### Starting a new conversation (from contacts list)
1. User taps a contact — open an empty chat screen (no API call yet)
2. User types and hits send
3. Send `sendMessage` with `targetUserId` (no `conversationId` yet)
4. On `messageAck` → store the returned `conversationId`
5. Use that `conversationId` for all future events in this chat

### Receiving a message from a new conversation (recipient side)
1. Server sends `newConversation` first → insert the conversation into your local inbox
2. Server immediately follows with `newMessage` → append the message to that conversation
3. The `otherUser` object in `newConversation` has everything needed to display the sender
   (cache it by `otherUser.id` for future lookups)

### Displaying user profiles
- Cache profiles in local storage (Hive/SQLite) keyed by `userId`
- On receiving any event with an unknown `senderId` → call `GET /users/{senderId}` once
- `newConversation.otherUser` already contains the sender profile — no extra call needed

### Sending a message
1. Send `sendMessage` over WS
2. Show message as "pending" in UI
3. On `messageAck` → mark as sent (single tick)
4. On `messageDelivered` → mark as delivered (double tick)
5. On `messageRead` → mark as read (blue double tick)

### Typing indicator
1. On text field change → send `typingStart` (debounce — not on every keystroke)
2. After 3s of no input → send `typingStop`
3. On receiving `typing` with `isTyping: true` → show "... is typing"
4. On `isTyping: false` → hide the indicator

### Heartbeat
1. On receiving `ping` → immediately send `pong`
2. Server closes with `4008` if no `pong` arrives within 90s

### Reconnection
```
on disconnect:
  wait 1s  → reconnect → send auth
  if fail: wait 2s  → reconnect → send auth
  if fail: wait 4s  → ...
  cap at 30s
```

---

## Data Types Reference

### ConversationOut

```
id               int
participant1Id   int        (always the lower user ID)
participant2Id   int        (always the higher user ID)
createdAt        datetime   ISO 8601, UTC
lastMessageAt    datetime   ISO 8601, UTC
```

### MessageOut

```
id               int
conversationId   int
senderId         int
content          string
messageType      "text" | "image" | "file"
status           "sent" | "delivered" | "read"
createdAt        datetime   ISO 8601, UTC
deliveredAt      datetime?  ISO 8601, UTC
readAt           datetime?  ISO 8601, UTC
```
