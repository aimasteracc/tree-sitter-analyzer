import { Cache, Store } from './store'

export function persist(store: Store, item: string): void {
  store.save(item)
}

export function remember(cache: Cache, item: string): void {
  cache.save(item)
}