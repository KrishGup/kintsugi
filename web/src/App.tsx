import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import { LlmProvider } from "./llm";
import Home from "./pages/Home";
import Session from "./pages/Session";

export default function App() {
  return (
    <AuthProvider>
      <LlmProvider>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/s/:id" element={<Session />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </LlmProvider>
    </AuthProvider>
  );
}
