import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { Toasts } from "./components/toast";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Toasts>
      <App />
    </Toasts>
  </StrictMode>,
);
