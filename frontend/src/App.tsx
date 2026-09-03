import { Route, Routes } from "react-router-dom";
import Layout from "./Layout";
import Dashboard from "./pages/Dashboard";
import Resumes from "./pages/Resumes";
import Jds from "./pages/Jds";
import Customizations from "./pages/Customizations";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="resumes" element={<Resumes />} />
        <Route path="jds" element={<Jds />} />
        <Route path="customizations" element={<Customizations />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
