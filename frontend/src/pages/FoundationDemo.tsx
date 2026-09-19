import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  Checkbox,
  Divider,
  FormControl,
  FormHelperText,
  FormLabel,
  Grid,
  HStack,
  Heading,
  Input,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  SimpleGrid,
  Stack,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  Textarea,
  useBreakpointValue,
  useDisclosure,
  VStack,
} from '@chakra-ui/react';
import { useCallback, useState } from 'react';
import { Section } from '@/components/common/Section';
import { StatusBadge } from '@/components/common/StatusBadge';
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Eye,
  FileImage,
  HeartPulse,
  Info,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  X,
  type LucideIcon,
} from '@/lib/icons';
import { kkuColors } from '@/theme/colors';

const TOKEN_SWATCHES: Array<{ name: string; hex: string; role: string }> = [
  { name: 'Brand anchor', hex: kkuColors.primary,     role: 'K K U  Red Soil' },
  { name: 'Brand dark',  hex: kkuColors.primaryDark, role: 'Deep Brick' },
  { name: 'Brand soft',  hex: kkuColors.primarySoft, role: 'Clay Tint' },
  { name: 'Warm accent', hex: kkuColors.accent,      role: 'Muted Gold' },
  { name: 'Ink',         hex: kkuColors.ink,         role: 'Primary text' },
  { name: 'Secondary',   hex: kkuColors.secondaryText, role: 'Helper text' },
  { name: 'Surface',     hex: kkuColors.surface,     role: 'App background' },
  { name: 'Panel',       hex: kkuColors.panel,       role: 'Card / panel' },
  { name: 'Border',      hex: kkuColors.border,      role: 'Divider' },
  { name: 'Info',        hex: kkuColors.info,        role: 'Status: info' },
  { name: 'Success',     hex: kkuColors.success,     role: 'Status: success' },
  { name: 'Warning',     hex: kkuColors.warning,     role: 'Status: warning' },
  { name: 'Danger',      hex: kkuColors.danger,      role: 'Status: danger' },
];

interface DemoRow {
  id: string;
  name: string;
  status: 'pending' | 'reviewed' | 'flagged';
  grade: number;
}

const demoRows: DemoRow[] = [
  { id: '01_dr',  name: 'Public sample · 01_dr',   status: 'reviewed', grade: 2 },
  { id: '02_dr',  name: 'Public sample · 02_dr',   status: 'pending',  grade: 1 },
  { id: 'SYNTH_001', name: 'Synthetic fixture',   status: 'flagged',  grade: 3 },
];

export function FoundationDemo() {
  const responsiveTitle = useBreakpointValue({
    base: '2xl',
    tablet: '3xl',
    laptop: '3xl',
  });

  return (
    <Box
      as="main"
      maxW="1280px"
      mx="auto"
      px={{ base: 4, tablet: 5, laptop: 7 }}
      py={{ base: 5, laptop: 6 }}
    >
      <Stack spacing={1} mb={5}>
        <Box
          as="span"
          fontSize="xxs"
          fontWeight="bold"
          letterSpacing="0.18em"
          textTransform="uppercase"
          color="brand.500"
        >
          Design system · v0.1
        </Box>
        <Heading as="h1" size={responsiveTitle} letterSpacing="-0.02em">
          Warm Clinical · KKU Contemporary
        </Heading>
        <Text fontSize="md" color="text.secondary" maxW="720px">
          Foundation scaffold preview. Brand anchor is the KKU red-soil
          ({kkuColors.primary}). Supporting neutrals, a single warm gold
          accent, and reserved status tones carry information hierarchy
          without competing with retinal imagery.
        </Text>
      </Stack>

      <Alert
        status="warning"
        variant="left-accent"
        borderRadius="md"
        mb={6}
        borderWidth="1px"
        borderColor="status.warning.border"
        bg="status.warning.bg"
      >
        <AlertIcon as={Info} boxSize="16px" />
        <Box>
          <AlertDescription fontSize="sm" color="text.primary">
            AI suggestion — requires clinician review. This page is a design
            preview only; no model inference is performed.
          </AlertDescription>
        </Box>
      </Alert>

      <Stack spacing={6}>
        <Section
          title="Color tokens"
          description="Semantic roles only — rest are derived from these."
        >
          <SimpleGrid columns={{ base: 2, tablet: 3, laptop: 4, desktop: 5 }} spacing={3}>
            {TOKEN_SWATCHES.map((s) => (
              <Swatch key={s.hex} name={s.name} hex={s.hex} role={s.role} />
            ))}
          </SimpleGrid>
        </Section>

        <Section
          title="Typography"
          description="Inter, semibold tracking -0.01em. Tight scale, no shouting headings."
        >
          <VStack align="stretch" spacing={3}>
            <Heading size="4xl" letterSpacing="-0.02em">
              Calibrate for clinical reading
            </Heading>
            <Text fontSize="lg">
              Body copy stays at 13–14px with a 1.5 line height so paragraphs
              breathe without leaving the operator head-down.
            </Text>
            <Text fontSize="sm" color="text.secondary">
              Helper / metadata tone uses the secondary text token at 12–13px.
            </Text>
            <Text fontFamily="mono" fontSize="sm" color="text.secondary">
              mono · retina-fundus · synthetic-fixture
            </Text>
          </VStack>
        </Section>

        <Section
          title="Buttons"
          description="Solid for primary CTA only; everything else stays restrained."
        >
          <HStack spacing={3} wrap="wrap">
            <Button leftIcon={<Save size={14} strokeWidth={2.25} />} variant="solid">
              Run analysis
            </Button>
            <Button variant="outline">View case</Button>
            <Button variant="secondary">Adjust grade</Button>
            <Button variant="danger" leftIcon={<X size={14} strokeWidth={2.25} />}>
              Escalate
            </Button>
            <Button variant="ghost">Cancel</Button>
            <Button isDisabled variant="solid">
              Disabled
            </Button>
          </HStack>
        </Section>

        <Section
          title="Status badges"
          description="Reserved tones for information hierarchy. Avoid using these decoratively."
        >
          <HStack spacing={2} wrap="wrap">
            <StatusBadge tone="neutral">Pending</StatusBadge>
            <StatusBadge tone="brand">Synthesized</StatusBadge>
            <StatusBadge tone="info">Imported</StatusBadge>
            <StatusBadge tone="success">Reviewed</StatusBadge>
            <StatusBadge tone="warning">Awaiting correction</StatusBadge>
            <StatusBadge tone="danger">Escalated</StatusBadge>
          </HStack>
        </Section>

        <Section
          title="Inputs"
          description="Form controls inherit the same restraint — 36px field height, subtle focus ring."
        >
          <SimpleGrid columns={{ base: 1, tablet: 2 }} spacing={4}>
            <FormControl>
              <FormLabel fontSize="xs">Case identifier</FormLabel>
              <Input value="SYNTH_001" readOnly />
              <FormHelperText fontSize="xs">
                Read-only sample case for the foundation preview.
              </FormHelperText>
            </FormControl>
            <FormControl>
              <FormLabel fontSize="xs">Reviewer note</FormLabel>
              <Textarea
                placeholder="Optional observation"
                rows={3}
                defaultValue="Image centred; lesion overlay aligned with vasculature."
              />
            </FormControl>
            <FormControl>
              <FormLabel fontSize="xs">Search</FormLabel>
              <Input placeholder="Find case or label" />
            </FormControl>
            <FormControl display="flex" flexDirection="column">
              <FormLabel fontSize="xs">Options</FormLabel>
              <Checkbox defaultChecked colorScheme="brand">
                Show lesion overlay
              </Checkbox>
              <Checkbox colorScheme="brand">Lock view zoom</Checkbox>
            </FormControl>
          </SimpleGrid>
        </Section>

        <Section
          title="Tables"
          description="Compact 14px body, low-contrast header, restrained dividers."
          action={
            <Button leftIcon={<Search size={14} />} variant="ghost" size="sm">
              Browse
            </Button>
          }
        >
          <Box overflowX="auto">
            <Table size="md" variant="clinical">
              <Thead>
                <Tr>
                  <Th>Case ID</Th>
                  <Th>Description</Th>
                  <Th isNumeric>Grade</Th>
                  <Th>Status</Th>
                </Tr>
              </Thead>
              <Tbody>
                {demoRows.map((r) => (
                  <Tr key={r.id}>
                    <Td fontWeight="bold">{r.id}</Td>
                    <Td>{r.name}</Td>
                    <Td isNumeric>{r.grade}</Td>
                    <Td>
                      <StatusBadge
                        tone={
                          r.status === 'reviewed'
                            ? 'success'
                            : r.status === 'pending'
                            ? 'neutral'
                            : 'warning'
                        }
                      >
                        {r.status}
                      </StatusBadge>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        </Section>

        <Section
          title="Status states & feedback"
          description="Soft tinted Alert panels, success confirmation, and an inline loading hint."
        >
          <Stack spacing={3}>
            <DemoDialogLauncher />
            <DemoToastLauncher />
            <Alert status="success" borderRadius="md" bg="status.success.bg">
              <AlertIcon as={CheckCircle2} boxSize="16px" />
              <AlertDescription fontSize="sm">
                Recorded grade 3 · persisted to local review state.
              </AlertDescription>
            </Alert>
            <Alert status="error" borderRadius="md" bg="status.danger.bg">
              <AlertIcon as={AlertTriangle} boxSize="16px" />
              <AlertDescription fontSize="sm">
                Inference failed. Inspect Models &amp; Audit for runtime status.
              </AlertDescription>
            </Alert>
            <Alert status="info" borderRadius="md" bg="status.info.bg">
              <AlertIcon as={Info} boxSize="16px" />
              <AlertDescription fontSize="sm">
                Awaiting CVAT round-trip — imported geometry will override
                suggestions when synced.
              </AlertDescription>
            </Alert>
          </Stack>
        </Section>

        <Section
          title="Iconography"
          description="Lucide-react only. Stroke 2.25, sized 14–18px in chrome."
        >
          <Grid
            templateColumns="repeat(auto-fit, minmax(120px, 1fr))"
            gap={3}
            color="text.secondary"
          >
            <IconTile icon={Stethoscope} label="Brand" />
            <IconTile icon={HeartPulse} label="Vital" />
            <IconTile icon={FileImage} label="Image" />
            <IconTile icon={Eye} label="Review" />
            <IconTile icon={ClipboardList} label="Worklist" />
            <IconTile icon={Sparkles} label="Suggestion" />
            <IconTile icon={ShieldCheck} label="Trust" />
          </Grid>
        </Section>

        <Divider borderColor="border.subtle" />

        <Box textAlign="center" color="text.secondary" fontSize="sm">
          <Text>Foundation build · v0.1</Text>
          <Text fontSize="xs" mt={1}>
            Next: Worklist migration, Case Review skeleton, react-router wiring.
          </Text>
        </Box>
      </Stack>
    </Box>
  );
}

function Swatch({ name, hex, role }: { name: string; hex: string; role: string }) {
  return (
    <VStack
      align="stretch"
      spacing={0}
      borderWidth="1px"
      borderColor="border.subtle"
      borderRadius="md"
      overflow="hidden"
      bg="surface.panel"
    >
      <Box bg={hex} h="44px" borderBottomWidth="1px" borderColor="border.subtle" />
      <VStack align="stretch" spacing={0} p={2.5}>
        <Text fontSize="xs" fontWeight="bold" color="text.primary">
          {name}
        </Text>
        <Text fontSize="xs" color="text.secondary" fontFamily="mono">
          {hex}
        </Text>
        <Text fontSize="xxs" color="text.muted" textTransform="uppercase" letterSpacing="0.06em">
          {role}
        </Text>
      </VStack>
    </VStack>
  );
}

function IconTile({
  icon: Icon,
  label,
}: {
  icon: LucideIcon;
  label: string;
}) {
  return (
    <VStack
      align="center"
      spacing={1.5}
      py={3}
      px={2}
      borderWidth="1px"
      borderColor="border.subtle"
      borderRadius="md"
      bg="surface.panel"
    >
      <Icon size={18} strokeWidth={2.25} />
      <Text fontSize="xs" color="text.secondary">
        {label}
      </Text>
    </VStack>
  );
}

function DemoDialogLauncher() {
  const { isOpen, onOpen, onClose } = useDisclosure();
  return (
    <Box>
      <HStack justify="space-between" align="center">
        <Box>
          <Text fontSize="md" fontWeight="bold">
            Modal pattern
          </Text>
          <Text fontSize="sm" color="text.secondary">
            Dialog overlays use a 12px radius with soft shadow, focus-trap, and
            the standard close affordance.
          </Text>
        </Box>
        <Button size="sm" variant="outline" onClick={onOpen}>
          Open
        </Button>
      </HStack>
      <Modal isOpen={isOpen} onClose={onClose} size="md">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Adjust grade</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Text fontSize="sm" color="text.secondary">
              Confirm a corrected grade. The suggestion will be marked as
              clinician-adjusted in the case event log.
            </Text>
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={2} onClick={onClose}>
              Cancel
            </Button>
            <Button variant="solid" onClick={onClose}>
              Confirm
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
}

function DemoToastLauncher() {
  const [open, setOpen] = useState(true);
  const handleClose = useCallback(() => setOpen(false), []);
  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Show inline notice
      </Button>
    );
  }
  return (
    <Alert status="info" borderRadius="md" bg="status.info.bg" alignItems="center">
      <AlertIcon as={Info} boxSize="16px" />
      <AlertDescription fontSize="sm">Inline notice pattern · dismissible.</AlertDescription>
      <Button size="xs" variant="ghost" ml="auto" onClick={handleClose} aria-label="Dismiss">
        Dismiss
      </Button>
    </Alert>
  );
}
