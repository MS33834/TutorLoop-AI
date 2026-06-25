import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '../chat.js'
import { useUserStore } from '../user.js'

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts with an empty default room', () => {
    const store = useChatStore()
    expect(store.messages).toEqual([])
    expect(store.currentRoomSlug).toBe('')
  })

  it('setRoom creates a per-user room key', () => {
    const user = useUserStore()
    user.setAuth('token', null, { id: 'u1' })

    const chat = useChatStore()
    chat.setRoom('room-a')

    expect(chat.currentRoomSlug).toBe('room-a')
    expect(chat.roomKey).toBe('u1:room-a')
    expect(chat.messages).toEqual([])
  })

  it('addMessage appends to the current room only', () => {
    const chat = useChatStore()
    chat.setRoom('room-a')
    chat.addMessage('user', 'hello')
    chat.addMessage('assistant', 'hi')

    expect(chat.messages).toHaveLength(2)
    expect(chat.messages[0].role).toBe('user')
    expect(chat.messages[1].role).toBe('assistant')

    chat.setRoom('room-b')
    expect(chat.messages).toEqual([])

    chat.setRoom('room-a')
    expect(chat.messages).toHaveLength(2)
  })

  it('appendAssistantToken concatenates to the last assistant message', () => {
    const chat = useChatStore()
    chat.setRoom('room-a')
    chat.addMessage('assistant', 'he')
    chat.appendAssistantToken('llo')

    expect(chat.messages[0].content).toBe('hello')
  })

  it('appendAssistantToken creates a new assistant message if last is not assistant', () => {
    const chat = useChatStore()
    chat.setRoom('room-a')
    chat.addMessage('user', '?')
    chat.appendAssistantToken('answer')

    expect(chat.messages).toHaveLength(2)
    expect(chat.messages[1].role).toBe('assistant')
    expect(chat.messages[1].content).toBe('answer')
  })

  it('updateLastAssistantContent replaces the last assistant content', () => {
    const chat = useChatStore()
    chat.setRoom('room-a')
    chat.addMessage('assistant', 'old')
    chat.updateLastAssistantContent('new')

    expect(chat.messages[0].content).toBe('new')
  })

  it('updateAssistantMessageById replaces a specific assistant message', () => {
    const chat = useChatStore()
    chat.setRoom('room-a')
    chat.addMessage('assistant', 'first')
    const targetId = chat.messages[0].id
    chat.addMessage('assistant', 'last')

    chat.updateAssistantMessageById(targetId, 'updated')

    expect(chat.messages[0].content).toBe('updated')
    expect(chat.messages[1].content).toBe('last')
  })

  it('appendAssistantTokenById appends to a specific assistant message', () => {
    const chat = useChatStore()
    chat.setRoom('room-a')
    chat.addMessage('assistant', 'he')
    const targetId = chat.messages[0].id
    chat.addMessage('assistant', 'other')

    chat.appendAssistantTokenById(targetId, 'llo')

    expect(chat.messages[0].content).toBe('hello')
    expect(chat.messages[1].content).toBe('other')
  })

  it('clearAll removes all rooms and resets state', () => {
    const chat = useChatStore()
    chat.setRoom('room-a')
    chat.addMessage('user', 'x')
    chat.clearAll()

    expect(chat.messagesMap.size).toBe(0)
    expect(chat.currentRoomSlug).toBe('')
  })
})
