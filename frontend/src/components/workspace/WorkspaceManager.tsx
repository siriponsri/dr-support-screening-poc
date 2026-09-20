import { useState, type FormEvent } from 'react';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Divider,
  FormControl,
  FormHelperText,
  FormLabel,
  HStack,
  IconButton,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Textarea,
  SimpleGrid,
  Spinner,
  Stack,
  Text,
  VStack,
} from '@chakra-ui/react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Copy, Database, FolderOpen, Pencil, Plus, RefreshCw, Save, Trash2, X } from '@/lib/icons';
import { Section } from '@/components/common/Section';
import { StatusBadge } from '@/components/common/StatusBadge';
import type { WorkspaceDraft, WorkspaceProfile } from '@/lib/api';
import { useWorkspace } from '@/components/shell/workspace';

type EditorMode = 'create' | 'edit';
type Feedback = { status: 'info' | 'success' | 'warning' | 'error'; message: string };

const EMPTY_DRAFT: WorkspaceDraft = {
  name: '',
  input_folder: '',
  output_folder: '',
  database_path: '',
  note: '',
};

function draftFromWorkspace(workspace: WorkspaceProfile): WorkspaceDraft {
  return {
    name: workspace.name,
    input_folder: workspace.input_folder,
    output_folder: workspace.output_folder,
    database_path: workspace.database_path,
    note: workspace.note ?? '',
  };
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : 'The workspace request could not be completed.';
}

function suggestedDatabaseName(path: string) {
  const filename = path.split(/[\\/]/).pop();
  return filename || 'review.sqlite';
}

export function WorkspaceManager() {
  const {
    workspaces,
    activeWorkspace,
    activeDatabase,
    status,
    warnings,
    error,
    isMutating,
    refresh,
    createWorkspace,
    updateWorkspace,
    openWorkspace,
    deleteWorkspace,
    pickFolder,
    pickDatabase,
  } = useWorkspace();
  const [editorMode, setEditorMode] = useState<EditorMode | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<WorkspaceDraft>(EMPTY_DRAFT);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [pickerLoading, setPickerLoading] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<WorkspaceProfile | null>(null);

  const beginCreate = () => {
    setEditorMode('create');
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setFeedback(null);
  };

  const beginEdit = (workspace: WorkspaceProfile) => {
    setEditorMode('edit');
    setEditingId(workspace.id);
    setDraft(draftFromWorkspace(workspace));
    setFeedback(null);
  };

  const closeEditor = () => {
    setEditorMode(null);
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
  };

  const updateDraft = (field: keyof WorkspaceDraft, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
    setFeedback((current) => current?.status === 'error' ? null : current);
  };

  const browseFolder = async (purpose: 'input' | 'output') => {
    const field = purpose === 'input' ? 'input_folder' : 'output_folder';
    setPickerLoading(field);
    setFeedback(null);
    try {
      const result = await pickFolder(purpose, draft[field]);
      if (result.status === 'selected' && result.path) {
        updateDraft(field, result.path);
        setFeedback({ status: 'success', message: `${purpose === 'input' ? 'Input' : 'Output'} folder selected.` });
      } else if (result.status === 'cancelled') {
        setFeedback({ status: 'info', message: 'Folder selection cancelled. The existing path was left unchanged.' });
      } else {
        setFeedback({
          status: 'warning',
          message: result.message || 'The native folder picker is unavailable. Enter an absolute local path manually.',
        });
      }
    } catch (pickerError) {
      setFeedback({ status: 'error', message: errorText(pickerError) });
    } finally {
      setPickerLoading(null);
    }
  };

  const browseDatabase = async (mode: 'open' | 'create') => {
    setPickerLoading(`database-${mode}`);
    setFeedback(null);
    try {
      const result = await pickDatabase(mode, draft.database_path, suggestedDatabaseName(draft.database_path));
      if (result.status === 'selected' && result.path) {
        updateDraft('database_path', result.path);
        setFeedback({ status: 'success', message: mode === 'create' ? 'New SQLite database location selected.' : 'SQLite database selected.' });
      } else if (result.status === 'cancelled') {
        setFeedback({ status: 'info', message: 'Database selection cancelled. The existing path was left unchanged.' });
      } else {
        setFeedback({
          status: 'warning',
          message: result.message || 'The native database picker is unavailable. Enter an absolute local SQLite path manually.',
        });
      }
    } catch (pickerError) {
      setFeedback({ status: 'error', message: errorText(pickerError) });
    } finally {
      setPickerLoading(null);
    }
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized: WorkspaceDraft = {
      name: draft.name.trim(),
      input_folder: draft.input_folder.trim(),
      output_folder: draft.output_folder.trim(),
      database_path: draft.database_path.trim(),
      note: draft.note?.trim() || null,
    };
    if (!normalized.name || !normalized.input_folder || !normalized.output_folder || !normalized.database_path) {
      setFeedback({ status: 'error', message: 'Name, input folder, output folder, and SQLite database are required.' });
      return;
    }
    if (normalized.name.length > 120) {
      setFeedback({ status: 'error', message: 'Workspace name must be 120 characters or fewer.' });
      return;
    }

    setFeedback(null);
    try {
      if (editorMode === 'edit' && editingId) {
        await updateWorkspace(editingId, normalized);
        setFeedback({ status: 'success', message: 'Workspace changes saved and opened.' });
      } else {
        await createWorkspace(normalized);
        setFeedback({ status: 'success', message: 'Workspace created and opened.' });
      }
      setDraft(normalized);
      setEditorMode(null);
      setEditingId(null);
    } catch (saveError) {
      setFeedback({ status: 'error', message: errorText(saveError) });
    }
  };

  const switchWorkspace = async (workspace: WorkspaceProfile) => {
    setFeedback(null);
    try {
      await openWorkspace(workspace.id);
      setFeedback({ status: 'success', message: `${workspace.name} is now the active workspace.` });
    } catch (openError) {
      setFeedback({ status: 'error', message: errorText(openError) });
    }
  };

  const removeWorkspace = async () => {
    if (!pendingDelete) return;
    const workspace = pendingDelete;
    setFeedback(null);
    try {
      await deleteWorkspace(workspace.id);
      setPendingDelete(null);
      setFeedback({ status: 'success', message: `${workspace.name} was removed from saved workspaces.` });
    } catch (deleteError) {
      setFeedback({ status: 'error', message: errorText(deleteError) });
    }
  };

  const copyPath = async (label: string, path: string) => {
    if (!path) return;
    try {
      await navigator.clipboard?.writeText(path);
      setFeedback({ status: 'success', message: `${label} copied.` });
    } catch {
      setFeedback({ status: 'warning', message: 'Copy is unavailable in this browser. Select the path to copy it manually.' });
    }
  };

  const initialLoading = status === 'loading' && workspaces.length === 0;
  const workspaceError = status === 'error' && error;

  return (
    <Stack spacing={5}>
      {feedback && <Alert status={feedback.status} role={feedback.status === 'error' ? 'alert' : undefined}><AlertIcon /><Text fontSize="sm">{feedback.message}</Text></Alert>}
      {warnings.length > 0 && (
        <Alert status="warning" alignItems="flex-start">
          <AlertIcon mt="2px" />
          <Stack spacing={1}>
            <Text fontSize="sm" fontWeight="semibold">Workspace service warning</Text>
            {warnings.map((warning) => <Text key={warning} fontSize="sm">{warning}</Text>)}
          </Stack>
        </Alert>
      )}
      {workspaceError && (
        <Alert status="error" alignItems="flex-start">
          <AlertIcon mt="2px" />
          <Stack spacing={2}>
            <Text fontSize="sm">{workspaceError}</Text>
            <Button size="sm" variant="outline" leftIcon={<RefreshCw size={14} />} onClick={() => void refresh()} w="fit-content">
              Retry
            </Button>
          </Stack>
        </Alert>
      )}
      {activeWorkspace && activeDatabase && (
        <Box borderWidth="1px" borderColor="border.subtle" borderRadius="lg" bg="surface.panel" p={{ base: 4, laptop: 5 }}>
          <HStack justify="space-between" align="flex-start" spacing={4} flexWrap="wrap">
            <Stack spacing={1} minW={0}>
              <Text fontSize="xxs" fontWeight="bold" textTransform="uppercase" letterSpacing="0.12em" color="text.secondary">Current workspace</Text>
              <Text fontSize="lg" fontWeight="semibold">{activeWorkspace.name}</Text>
              {activeWorkspace.note && <Text fontSize="sm" color="text.secondary" noOfLines={2} title={activeWorkspace.note}>{activeWorkspace.note}</Text>}
              <Text fontSize="sm" color="text.secondary">Opening a workspace changes this process's active review database. It does not move or copy images.</Text>
            </Stack>
            <HStack spacing={2} align="center">
              <StatusBadge tone="brand"><CheckCircle2 size={11} aria-hidden="true" /> Active</StatusBadge>
              <Button size="sm" variant="outline" leftIcon={<Pencil size={14} />} onClick={() => beginEdit(activeWorkspace)}>Edit</Button>
            </HStack>
          </HStack>
          <HStack mt={3} spacing={2} align="flex-start">
            <Database size={15} color="var(--chakra-colors-text-secondary)" aria-hidden="true" />
            <Text fontSize="sm" fontFamily="mono" wordBreak="break-all" title={activeDatabase.path}>{activeDatabase.path}</Text>
            <IconButton aria-label="Copy active database path" icon={<Copy size={14} />} size="sm" variant="ghost" onClick={() => void copyPath('Database path', activeDatabase.path)} />
          </HStack>
        </Box>
      )}
      <SimpleGrid columns={{ base: 1, laptop: editorMode ? 2 : 1 }} gap={5} alignItems="start">
        <Section
          title="Saved workspaces"
          description="Profiles keep local folders and the SQLite review database together."
          action={
            <Button size="sm" variant="solid" leftIcon={<Plus size={14} />} onClick={beginCreate}>
              New workspace
            </Button>
          }
        >
          {initialLoading ? (
            <HStack py={8} justify="center" color="text.secondary"><Spinner size="sm" /><Text fontSize="sm">Loading workspaces</Text></HStack>
          ) : workspaces.length === 0 ? (
            <Box borderWidth="1px" borderStyle="dashed" borderColor="border.default" borderRadius="md" bg="surface.subtle" p={5}>
              <Stack spacing={2}>
                <Text fontWeight="semibold">No workspaces saved</Text>
                <Text fontSize="sm" color="text.secondary">Create a profile to choose the local input folder, output folder, and SQLite database for this review station.</Text>
                <Button size="sm" variant="secondary" leftIcon={<Plus size={14} />} onClick={beginCreate} w="fit-content">Create the first workspace</Button>
              </Stack>
            </Box>
          ) : (
            <Stack spacing={0} divider={<Divider borderColor="border.subtle" />}>
              {workspaces.map((workspace) => (
                <WorkspaceRow
                  key={workspace.id}
                  workspace={workspace}
                  active={workspace.id === activeWorkspace?.id}
                  onSwitch={() => void switchWorkspace(workspace)}
                  onEdit={() => beginEdit(workspace)}
                  onDelete={() => setPendingDelete(workspace)}
                  isMutating={isMutating}
                />
              ))}
            </Stack>
          )}
          {status === 'loading' && workspaces.length > 0 && <Text mt={3} fontSize="xs" color="text.secondary">Refreshing workspace catalog…</Text>}
        </Section>
        {editorMode && (
          <Section
            title={editorMode === 'create' ? 'Create workspace' : 'Edit workspace'}
            description="Paths are local configuration. Saving creates or opens the selected SQLite database."
            action={<IconButton aria-label="Close workspace editor" icon={<X size={16} />} size="sm" variant="ghost" onClick={closeEditor} />}
          >
            <form onSubmit={save}>
              <Stack spacing={4}>
                <FormControl isRequired>
                  <FormLabel htmlFor="workspace-name">Workspace name</FormLabel>
                  <Input id="workspace-name" aria-label="Workspace name" value={draft.name} maxLength={120} onChange={(event) => updateDraft('name', event.target.value)} placeholder="e.g. April DR screening" autoFocus />
                  <FormHelperText>Required; up to 120 characters.</FormHelperText>
                </FormControl>
                <FormControl>
                  <FormLabel htmlFor="workspace-note">Workspace note (optional)</FormLabel>
                  <Textarea id="workspace-note" aria-label="Workspace note" value={draft.note ?? ''} maxLength={500} onChange={(event) => updateDraft('note', event.target.value)} placeholder="e.g. Mobile screening unit - Sept 2026" resize="vertical" rows={3} />
                  <FormHelperText>Optional; up to 500 characters. Leave blank to clear it.</FormHelperText>
                </FormControl>
                <PathField label="Input folder" value={draft.input_folder} onChange={(value) => updateDraft('input_folder', value)} onBrowse={() => void browseFolder('input')} onCopy={() => void copyPath('Input folder', draft.input_folder)} isLoading={pickerLoading === 'input_folder'} />
                <PathField label="Output folder" value={draft.output_folder} onChange={(value) => updateDraft('output_folder', value)} onBrowse={() => void browseFolder('output')} onCopy={() => void copyPath('Output folder', draft.output_folder)} isLoading={pickerLoading === 'output_folder'} />
                <FormControl isRequired>
                  <FormLabel htmlFor="workspace-database">SQLite database</FormLabel>
                  <HStack align="stretch">
                    <Input id="workspace-database" aria-label="SQLite database" flex={1} value={draft.database_path} onChange={(event) => updateDraft('database_path', event.target.value)} placeholder="C:\\Data\\review.sqlite" fontFamily="mono" title={draft.database_path} />
                    <IconButton aria-label="Copy SQLite database path" icon={<Copy size={14} />} size="sm" variant="ghost" onClick={() => void copyPath('Database path', draft.database_path)} isDisabled={!draft.database_path} />
                  </HStack>
                  <HStack mt={2} spacing={2} flexWrap="wrap">
                    <Button size="sm" variant="outline" leftIcon={<FolderOpen size={14} />} onClick={() => void browseDatabase('open')} isLoading={pickerLoading === 'database-open'} isDisabled={Boolean(pickerLoading)}>Open existing</Button>
                    <Button size="sm" variant="secondary" leftIcon={<Database size={14} />} onClick={() => void browseDatabase('create')} isLoading={pickerLoading === 'database-create'} isDisabled={Boolean(pickerLoading)}>Choose new database</Button>
                  </HStack>
                  <FormHelperText>The database is initialized when this workspace is saved; existing case data is preserved.</FormHelperText>
                </FormControl>
                <Alert status="info" alignItems="flex-start">
                  <AlertIcon mt="2px" />
                  <Text fontSize="sm">Browse uses the local FastAPI process's native dialog. If it is unavailable, enter an absolute local path manually.</Text>
                </Alert>
                <HStack justify="flex-end" spacing={2}>
                  <Button type="button" size="sm" variant="ghost" leftIcon={<X size={14} />} onClick={closeEditor}>Cancel</Button>
                  <Button type="submit" size="sm" variant="solid" leftIcon={editorMode === 'create' ? <Plus size={14} /> : <Save size={14} />} isLoading={isMutating} isDisabled={Boolean(pickerLoading)}>
                    {editorMode === 'create' ? 'Create workspace' : 'Save changes'}
                  </Button>
                </HStack>
              </Stack>
            </form>
          </Section>
        )}
      </SimpleGrid>
      <Text fontSize="xs" color="text.secondary">Workspace selection changes local review context only. It does not imply that files were moved, copied, uploaded, or sent to a model service.</Text>
      <Modal isOpen={Boolean(pendingDelete)} onClose={() => setPendingDelete(null)} isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Delete workspace profile?</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Stack spacing={3}>
              <Text>Remove <Text as="span" fontWeight="semibold">{pendingDelete?.name}</Text> from the saved workspace catalog?</Text>
              <Text fontSize="sm" color="text.secondary">This removes only the workspace profile. Local input/output folders, retinal images, SQLite review data, and model data files will not be deleted.</Text>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <HStack spacing={2}>
              <Button variant="ghost" onClick={() => setPendingDelete(null)} isDisabled={isMutating}>Cancel</Button>
              <Button variant="danger" leftIcon={<Trash2 size={14} />} onClick={() => void removeWorkspace()} isLoading={isMutating}>Delete profile</Button>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Stack>
  );
}

function PathField({ label, value, onChange, onBrowse, onCopy, isLoading }: { label: string; value: string; onChange: (value: string) => void; onBrowse: () => void; onCopy: () => void; isLoading: boolean }) {
  const fieldId = label.toLowerCase().replace(/[^a-z]+/g, '-');
  return (
    <FormControl isRequired>
      <FormLabel htmlFor={fieldId}>{label}</FormLabel>
      <HStack align="stretch">
        <Input id={fieldId} aria-label={label} flex={1} value={value} onChange={(event) => onChange(event.target.value)} placeholder="C:\\Data\\folder" fontFamily="mono" title={value} />
        <IconButton aria-label={`Copy ${label.toLowerCase()}`} icon={<Copy size={14} />} size="sm" variant="ghost" onClick={onCopy} isDisabled={!value} />
        <Button size="sm" variant="outline" aria-label={`Browse ${label.toLowerCase()}`} leftIcon={<FolderOpen size={14} />} onClick={onBrowse} isLoading={isLoading} isDisabled={isLoading}>Browse</Button>
      </HStack>
    </FormControl>
  );
}

function WorkspaceRow({ workspace, active, onSwitch, onEdit, onDelete, isMutating }: { workspace: WorkspaceProfile; active: boolean; onSwitch: () => void; onEdit: () => void; onDelete: () => void; isMutating: boolean }) {
  return (
    <Box role="group" aria-label={`${workspace.name} workspace`} py={4} px={1} borderLeftWidth="3px" borderLeftColor={active ? 'action.primary' : 'transparent'} pl={active ? 3 : 4}>
      <HStack align="flex-start" justify="space-between" spacing={4} flexWrap="wrap">
        <Stack spacing={1} minW={0} flex={1}>
          <Text flex={1} minW={0} fontWeight="semibold" noOfLines={1} title={workspace.name}>{workspace.name}</Text>
          {workspace.note && <Text fontSize="xs" color="text.secondary" noOfLines={2} title={workspace.note}>{workspace.note}</Text>}
        </Stack>
        <HStack spacing={2} align="center" flexShrink={0} flexWrap="wrap" justify="flex-end">
          {active ? <StatusBadge tone="brand"><CheckCircle2 size={11} aria-hidden="true" /> Active</StatusBadge> : <Button size="sm" width="152px" justifyContent="center" variant="solid" onClick={onSwitch} isLoading={isMutating}>Switch</Button>}
          <Button size="sm" width="152px" justifyContent="center" variant="outline" leftIcon={<Pencil size={14} />} onClick={onEdit} isDisabled={isMutating}>Edit</Button>
          {!active && <Button size="sm" variant="danger" leftIcon={<Trash2 size={14} />} onClick={onDelete} isDisabled={isMutating}>Delete</Button>}
        </HStack>
      </HStack>
    </Box>
  );
}
