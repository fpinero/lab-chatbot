import { useEffect, useState } from "react";

const desktopInteraction = "(hover: hover) and (pointer: fine)";

export function useEnterToSend() {
  const [enabled, setEnabled] = useState(
    () =>
      typeof window.matchMedia === "function" &&
      window.matchMedia(desktopInteraction).matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(desktopInteraction);
    const change = () => setEnabled(query.matches);
    change();
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  return enabled;
}
