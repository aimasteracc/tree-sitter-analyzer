export class Target {
  #secret = 1
  run(): number {
    return this.#secret
  }
}

export class Other {
  private hidden = 2
  run(): number {
    return this.hidden
  }
}

export class Loose {
  run(): number {
    return 3
  }
}

export interface Runner {
  run(): number
}

export class Sub extends Target {
  run(): number {
    return 4
  }
}