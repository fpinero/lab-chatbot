import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import App from '../src/App';

test('preview is explicit and visibly simulated', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify({ environment: 'test', simulated: true })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ text: 'Local preview: Hello', simulated: true })));
  render(<App />);
  await screen.findByText('Local service connected');
  await userEvent.type(screen.getByLabelText('Preview prompt'), 'Hello');
  expect(fetcher).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole('button', { name: /Run preview/ }));
  expect(await screen.findByText('Local preview: Hello')).toBeVisible();
  expect(screen.getByText(/No requests leave this device/)).toBeVisible();
});

test('a failed preview preserves the draft for a deliberate retry', async () => {
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response('{}'))
    .mockResolvedValueOnce(new Response('{}', { status: 503 }));
  render(<App />);
  await screen.findByText('Local service connected');
  await userEvent.type(screen.getByLabelText('Preview prompt'), 'Keep my draft');
  await userEvent.click(screen.getByRole('button', { name: /Run preview/ }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Try again'));
  expect(screen.getByLabelText('Preview prompt')).toHaveValue('Keep my draft');
});
