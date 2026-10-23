import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";

import { App } from "../App";
import { Providers } from "../Providers";

export function testClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

let location = "";
function LocationProbe() {
  location = useLocation().pathname;
  return null;
}

// The whole app at `path`, with the API served by an installFakeApi() set up beforehand.
export function renderApp(path = "/") {
  const result = render(
    <Providers client={testClient()}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <LocationProbe />
      </MemoryRouter>
    </Providers>,
  );
  return { ...result, location: () => location };
}
