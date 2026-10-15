
import { ChakraProvider } from '@chakra-ui/react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfirmImageDialog } from '@/components/worklist/ConfirmImageDialog';
import { admissionApi, type CaseRecord } from '@/lib/api';
import { setDefaultReviewer } from '@/lib/reviewerPreference';
import { theme } from '@/theme';

const item: CaseRecord = {
  image_id: 'synthetic-confirm-ui', display_name: 'synthetic.png', filename: 'synthetic.png',
  source_type: 'SYNTHETIC', source: 'fixture', modality: 'UWF',
  width: 640, height: 480, image_url: null, state: 'PENDING', revision: 7,
  global: null, lesion: null, lesion_review: null, human_annotations: [],
  clinician_review: null, admission: null, admission_ui: null,
  patient_key: 'SYNTHETIC-INVALID', laterality: 'LEFT',
};

function openDialog(record = item) {
  const onSaved = vi.fn();
  const onClose = vi.fn();
  const view = render(
    <ChakraProvider theme={theme}>
      <ConfirmImageDialog item={record} onSaved={onSaved} onClose={onClose} />
    </ChakraProvider>,
  );
  return { ...view, onSaved, onClose };
}

beforeEach(() => {
  window.localStorage.clear();
  setDefaultReviewer('Synthetic reviewer');
});

describe('Confirm Image error recovery', () => {
  it('reveals and focuses a rejected collapsed patient key, preserves context, and retries with the correction', async () => {
    const user = userEvent.setup();
    const save = vi.spyOn(admissionApi, 'confirmImage')
      .mockRejectedValueOnce(new Error('Patient key must be a short pseudonymous identifier'))
      .mockResolvedValueOnce(item);
    const { onSaved, onClose } = openDialog();
    expect(screen.queryByLabelText('Patient')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Additional metadata' })).toHaveAttribute('aria-expanded', 'false');

    await user.click(screen.getByRole('button', { name: 'Confirm image & continue' }));
    const input = await screen.findByLabelText('Patient');
    expect(input).toHaveValue('SYNTHETIC-INVALID');
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    await waitFor(() => expect(input).toHaveFocus());
    expect(input).toHaveAccessibleDescription(/starting with a letter and including a number/);
    expect(screen.queryByRole('button', { name: 'Edit patient' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit eye' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Additional metadata' })).toHaveAttribute('aria-expanded', 'false');
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, 'demo009');
    expect(input).not.toHaveAttribute('aria-invalid', 'true');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(item));
    expect(save).toHaveBeenLastCalledWith(item.image_id, expect.objectContaining({
      revision: 7, patient_key: 'DEMO009', laterality: 'LEFT', retinal_modality: 'UWF',
      reviewer: 'Synthetic reviewer', capture_sequence: null,
    }));
  });

  it('allows the rejected key to be cleared and saved unlinked without inventing a replacement', async () => {
    const user = userEvent.setup();
    const save = vi.spyOn(admissionApi, 'confirmImage')
      .mockRejectedValueOnce(new Error('Patient key must be a short pseudonymous identifier'))
      .mockResolvedValueOnce(item);
    openDialog();
    await user.click(screen.getByRole('button', { name: 'Confirm image & continue' }));
    await user.clear(await screen.findByLabelText('Patient'));
    await user.click(screen.getByRole('button', { name: 'Confirm image & continue' }));
    expect(save).toHaveBeenLastCalledWith(item.image_id, expect.objectContaining({ patient_key: null }));
  });

  it('keeps unexpected exception details out of the clinician alert and retains entered values', async () => {
    const user = userEvent.setup();
    vi.spyOn(admissionApi, 'confirmImage').mockRejectedValue(new Error('internal exception: synthetic debug detail'));
    openDialog();
    await user.click(screen.getByRole('button', { name: 'Edit patient' }));
    await user.clear(screen.getByLabelText('Patient'));
    await user.type(screen.getByLabelText('Patient'), 'demo008');
    await user.click(screen.getByRole('button', { name: 'Confirm image & continue' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Image confirmation could not be saved. Check your entries and try again.');
    expect(screen.queryByText(/internal exception/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('Patient')).toHaveValue('DEMO008');
  });
});

