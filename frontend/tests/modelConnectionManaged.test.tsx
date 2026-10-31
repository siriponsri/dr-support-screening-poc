import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { ModelConnectionSettings } from '@/components/settings/ModelConnectionSettings';

function reply(body: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => body })));
}

const base = {
  name: 'dr-train M1', url: 'http://127.0.0.1:47860', token_configured: true, status: 'CONNECTED',
  message: 'Connected to the model server. Each result is checked when it is saved.', server_reachable: true,
  api_contract_valid: true, connection_verified: true, capabilities_ready: true, models: [],
};

afterEach(() => { vi.unstubAllGlobals(); });

describe('operator-managed model connection', () => {
  it('shows status only, with no URL or token entry and no save', async () => {
    reply({ ...base, managed_by_operator: true });
    render(<ChakraProvider><ModelConnectionSettings /></ChakraProvider>);
    expect(await screen.findByTestId('model-connection-managed')).toHaveTextContent('configured by the operator');
    expect(screen.queryByLabelText(/Access token/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Model API URL/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Save/ })).not.toBeInTheDocument();
  });
  it('keeps the generic editable form when the connection is not operator-managed', async () => {
    reply({ ...base, managed_by_operator: false });
    render(<ChakraProvider><ModelConnectionSettings /></ChakraProvider>);
    expect(await screen.findByLabelText(/Access token/)).toBeInTheDocument();
    expect(screen.queryByTestId('model-connection-managed')).not.toBeInTheDocument();
  });
});
