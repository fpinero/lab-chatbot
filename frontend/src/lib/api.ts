import type { components } from '../generated/api';

type BootstrapInfo = components['schemas']['BootstrapInfo'];
type PreviewResult = components['schemas']['PreviewResult'];

export async function bootstrap(): Promise<BootstrapInfo> {
  const response = await fetch('/api/dev/bootstrap');
  if (!response.ok) throw new Error('bootstrap_failed');
  return response.json() as Promise<BootstrapInfo>;
}

export async function preview(prompt: string): Promise<PreviewResult> {
  const response = await fetch('/api/dev/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }),
  });
  if (!response.ok) throw new Error('preview_failed');
  return response.json() as Promise<PreviewResult>;
}
