import { adaptCatalog } from "./catalogAdapter.js";
import { fetchCatalog } from "./catalogApi.js";

const INITIAL_STATE = Object.freeze({
  status: "idle",
  catalog: null,
  error: null,
});

export function createCatalogResource({
  fetchCatalogImpl = fetchCatalog,
  adaptCatalogImpl = adaptCatalog,
  apiOptions,
} = {}) {
  let state = INITIAL_STATE;
  let requestSequence = 0;
  const listeners = new Set();

  function publish(nextState) {
    state = Object.freeze(nextState);
    for (const listener of listeners) {
      listener(state);
    }
  }

  return {
    getState() {
      return state;
    },

    subscribe(listener) {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },

    async load() {
      const requestId = ++requestSequence;
      publish({ status: "loading", catalog: null, error: null });

      try {
        const payload = await fetchCatalogImpl(apiOptions);
        const catalog = adaptCatalogImpl(payload);
        if (requestId !== requestSequence) {
          return state;
        }

        publish({
          status: catalog.categories.length ? "ready" : "empty",
          catalog,
          error: null,
        });
      } catch (error) {
        if (requestId !== requestSequence) {
          return state;
        }

        publish({ status: "error", catalog: null, error });
      }

      return state;
    },
  };
}
