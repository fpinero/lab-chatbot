export const isRunTerminal = (status: string) =>
  ["succeeded", "failed", "cancelled", "interrupted"].includes(status);
