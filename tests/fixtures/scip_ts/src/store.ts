export class Store {
  private items: string[] = []
  save(item: string): void {
    this.items.push(item)
  }
}

export class Cache {
  #entries = new Map<string, string>()
  save(item: string): void {
    this.#entries.set(item, item)
  }
}