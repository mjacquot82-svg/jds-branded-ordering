// The readable order number a shop already sees in its queue ("ZTC-000010").
// Customer-facing screens show this, never the public access token: the token is the
// unguessable key in URLs and must stay out of anything a person reads or prints.
export function orderReference(order) {
  const value = order?.reference;
  return typeof value === "string" ? value.trim() : "";
}
