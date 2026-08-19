export function addToCart(cart, product) {
  const existing = cart.find((item) => item.id === product.id);

  if (existing) {
    return cart.map((item) =>
      item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item
    );
  }

  return [...cart, { ...product, quantity: 1 }];
}

export function removeFromCart(cart, productId) {
  return cart.filter((item) => item.id !== productId);
}

export function getCartTotal(cart) {
  return cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
}
