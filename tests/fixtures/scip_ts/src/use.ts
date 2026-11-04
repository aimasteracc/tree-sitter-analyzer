import { Loose, Other, Runner, Sub, Target } from './shapes'

export function viaTarget(t: Target): number {
  return t.run()
}

export function viaOther(o: Other): number {
  return o.run()
}

export function viaLoose(l: Loose): number {
  return l.run()
}

export function viaIface(r: Runner): number {
  return r.run()
}

export function viaSub(s: Sub): number {
  return s.run()
}

export function both(t: Target, o: Other): number {
  return t.run() + o.run()
}

export function commented(t: Target): number {
  return t.run() // run twice?
}