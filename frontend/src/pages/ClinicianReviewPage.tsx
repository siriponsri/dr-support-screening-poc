import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  Alert,
  AlertIcon,
  Box,
  Button,
  Center,
  FormControl,
  FormLabel,
  Grid,
  Heading,
  HStack,
  Input,
  Select,
  SimpleGrid,
  Spinner,
  Stack,
  Text,
  Textarea,
} from '@chakra-ui/react';
import { PageHeader } from '@/components/common/PageHeader';
import { Section } from '@/components/common/Section';
import { RetinalCanvas } from '@/components/review/RetinalCanvas';
import { apiJson, type CaseRecord } from '@/lib/api';
import { ArrowLeft, Check, Flag, ShieldCheck, ThumbsDown } from '@/lib/icons';

type ReviewAction = 'ACCEPT' | 'MARK_INCORRECT' | 'CORRECT_GRADE' | 'ESCALATE';

function errorText(err: unknown) {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

function reviewLabel(item: CaseRecord) {
  if (item.state === 'REVIEWED') return 'Reviewed';
  if (item.state === 'NEEDS_CORRECTION') return 'Needs correction';
  if (item.state === 'ESCALATED') return 'Escalated';
  return 'Pending review';
}

export function ClinicianReviewPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [reviewer, setReviewer] = useState('');
  const [grade, setGrade] = useState('');
  const [remark, setRemark] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingAction, setSavingAction] = useState<ReviewAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadCase = useCallback(async () => {
    if (!imageId) return;
    setLoading(true);
    setError(null);
    try {
      const loaded = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}`);
      setItem(loaded);
      if (loaded.clinician_review) {
        setReviewer(loaded.clinician_review.reviewer);
        setRemark(loaded.clinician_review.remark);
        setGrade(loaded.clinician_review.final_grade === null ? '' : String(loaded.clinician_review.final_grade));
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [imageId]);

  useEffect(() => { void loadCase(); }, [loadCase]);

  const saveReview = async (action: ReviewAction) => {
    if (!item || savingAction) return;
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return;
    }
    if (action === 'CORRECT_GRADE' && grade === '') {
      setError('Choose a final DR grade before saving a correction.');
      return;
    }
    setSavingAction(action);
    setError(null);
    setSuccess(null);
    try {
      const saved = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: item.revision,
          action,
          reviewer: reviewer.trim(),
          grade: action === 'CORRECT_GRADE' ? Number(grade) : null,
          comment: remark,
        }),
      });
      setItem(saved);
      setSuccess(`${action === 'ACCEPT' ? 'AI grade accepted' : action === 'CORRECT_GRADE' ? 'Final grade saved' : action === 'MARK_INCORRECT' ? 'AI output marked incorrect' : 'Case escalated'} for ${saved.display_name}.`);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSavingAction(null);
    }
  };

  if (!imageId) return <Center minH="360px"><Text>Select an image from the Worklist.</Text></Center>;
  if (loading && !item) return <Center minH="360px"><Spinner color="action.primary" /></Center>;
  if (error && !item) return <Box as="main" maxW="1440px" mx="auto" px={6} py={6}><Alert status="error"><AlertIcon /><Text>{error}</Text></Alert><Button mt={4} onClick={() => navigate('/worklist')}>Back to Worklist</Button></Box>;
  if (!item) return null;

  return (
    <Box as="main" maxW="1440px" mx="auto" px={{ base: 4, tablet: 5, laptop: 7 }} py={{ base: 5, tablet: 6 }}>
      <PageHeader
        pathname={pathname}
        title="Clinician Review"
        subtitle={`${item.display_name} - human sign-off and review record`}
        actions={<HStack><Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} leftIcon={<ArrowLeft size={15} />}>Back to AI Review</Button><Button as={Link} to="/worklist">Back to Worklist</Button></HStack>}
      />
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.25fr) minmax(320px, 0.75fr)' }} gap={5} alignItems="start">
        <Section title="Review summary" description="AI output is a suggestion; this page records the clinician decision. ">
          <RetinalCanvas item={item} showAi={false} showHuman={true} />
          <SimpleGrid columns={{ base: 1, tablet: 3 }} spacing={4} mt={4}>
            <Stack spacing={1}><Text fontSize="sm" color="text.secondary">AI-predicted grade</Text><Heading size="md">{item.global?.grade === null || item.global === null ? 'Not analyzed' : `Grade ${item.global.grade}`}</Heading></Stack>
            <Stack spacing={1}><Text fontSize="sm" color="text.secondary">Human annotations</Text><Heading size="md">{item.human_annotations?.length ?? 0}</Heading></Stack>
            <Stack spacing={1}><Text fontSize="sm" color="text.secondary">AI lesion suggestions</Text><Heading size="md">{item.lesion_review?.suggestion_count ?? 0}</Heading></Stack>
          </SimpleGrid>
          <HStack mt={4} justify="space-between" align="center" borderTopWidth="1px" borderColor="border.subtle" pt={4}>
            <Text color="text.secondary">Current review state</Text>
            <Text fontWeight="semibold">{reviewLabel(item)}</Text>
          </HStack>
          {item.clinician_review && <Text mt={3} fontSize="sm" color="text.secondary">Last saved by {item.clinician_review.reviewer} - {new Date(item.clinician_review.timestamp).toLocaleString()}</Text>}
        </Section>
        <Stack spacing={5}>
          <Section title="Clinician sign-off" description="Save a human review action with an optional remark.">
            <Stack spacing={4}>
              <FormControl isRequired>
                <FormLabel>Reviewer name</FormLabel>
                <Input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" />
              </FormControl>
              <FormControl>
                <FormLabel>Final DR grade</FormLabel>
                <Select value={grade} onChange={(event) => setGrade(event.target.value)} placeholder="Select grade 0-4">
                  {[0, 1, 2, 3, 4].map((value) => <option key={value} value={value}>Grade {value}</option>)}
                </Select>
              </FormControl>
              <FormControl>
                <FormLabel>Remark</FormLabel>
                <Textarea value={remark} onChange={(event) => setRemark(event.target.value)} placeholder="Add a review remark" rows={5} />
              </FormControl>
              {error && <Alert status="error"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
              {success && <Alert status="success"><AlertIcon /><Text fontSize="sm">{success}</Text></Alert>}
              <Stack spacing={2}>
                <Button variant="solid" leftIcon={<Check size={15} />} onClick={() => void saveReview('ACCEPT')} isLoading={savingAction === 'ACCEPT'} isDisabled={item.global?.grade == null || Boolean(savingAction)}>Accept AI grade</Button>
                <Button leftIcon={<ShieldCheck size={15} />} variant="secondary" onClick={() => void saveReview('CORRECT_GRADE')} isLoading={savingAction === 'CORRECT_GRADE'} isDisabled={Boolean(savingAction)}>Correct / set grade</Button>
                <Button leftIcon={<ThumbsDown size={15} />} variant="outline" onClick={() => void saveReview('MARK_INCORRECT')} isLoading={savingAction === 'MARK_INCORRECT'} isDisabled={Boolean(savingAction)}>Mark AI incorrect</Button>
                <Button leftIcon={<Flag size={15} />} variant="outline" onClick={() => void saveReview('ESCALATE')} isLoading={savingAction === 'ESCALATE'} isDisabled={Boolean(savingAction)}>Escalate</Button>
              </Stack>
            </Stack>
          </Section>
          <Section title="Review record" description="Persisted in the existing SQLite case store.">
            {item.clinician_review ? (
              <Stack spacing={2} fontSize="sm">
                <Text><strong>Action:</strong> {item.clinician_review.review_action}</Text>
                <Text><strong>Final grade:</strong> {item.clinician_review.final_grade === null ? 'Not set' : item.clinician_review.final_grade}</Text>
                <Text><strong>Remark:</strong> {item.clinician_review.remark || 'None'}</Text>
                <Text fontSize="xs" color="text.muted">Revision {item.clinician_review.revision}</Text>
              </Stack>
            ) : <Text color="text.secondary">No clinician review saved yet.</Text>}
          </Section>
        </Stack>
      </Grid>
    </Box>
  );
}
