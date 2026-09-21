import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import Defects from "./pages/Defects";
import Runs from "./pages/Runs";
import RunPage from "./pages/Run";
import CandidatePage from "./pages/Candidate";
import Reports from "./pages/Reports";
import About from "./pages/About";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Defects /> },
      { path: "runs", element: <Runs /> },
      { path: "runs/:runId", element: <RunPage /> },
      { path: "runs/:runId/candidates/:candidateId", element: <CandidatePage /> },
      { path: "reports", element: <Reports /> },
      { path: "about", element: <About /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
