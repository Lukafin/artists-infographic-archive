// Ideal DC source, ohmic resistor, zero-resistance wires and ammeter.
export function circuit({voltage=6,resistance=12,closed=true}={}) {
  if(!Number.isFinite(voltage)||voltage<0||voltage>12) throw new RangeError('voltage: 0–12 V');
  if(!Number.isFinite(resistance)||resistance<4||resistance>24) throw new RangeError('resistance: 4–24 Ω');
  const current=closed?voltage/resistance:0;
  return {voltage,resistance,closed:Boolean(closed),current,power:voltage*current};
}
