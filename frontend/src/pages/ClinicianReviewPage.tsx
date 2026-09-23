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
  Radio,
  RadioGroup,
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
import { ArrowLeft } from '@/lib/icons';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { ReviewerField } from '@/components/common/ReviewerField';
import { CaseNavigation } from '@/components/common/CaseNavigation';
import { NextActionHint } from '@/components/common/NextActionHint';

type ReviewAction = 'ACCEPT' | 'CORRECT_GRADE' | 'ESCALATE';
type ReviewDecision = 'FINAL_GRADE' | 'SENIOR_REVIEW';

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
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [useAsDefault, setUseAsDefault] = useState(() => Boolean(getDefaultReviewer()));
  const [grade, setGrade] = useState('');
  const [decision, setDecision] = useState<ReviewDecision>('FINAL_GRADE');
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
      setReviewer(loaded.clinician_review?.reviewer ?? getDefaultReviewer());
      setUseAsDefault(Boolean(getDefaultReviewer()));
      if (loaded.clinician_review) {
        setRemark(loaded.clinician_review.remark);
        setGrade(loaded.clinician_review.final_grade === null ? '' : String(loaded.clinician_review.final_grade));
        setDecision(loaded.clinician_review.review_action === 'ESCALATE' ? 'SENIOR_REVIEW' : 'FINAL_GRADE');
      } else {
        setDecision('FINAL_GRADE');
      }
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      setLoading(false);
    }
  }, [imageId]);

  useEffect(() => { void loadCase(); }, [loadCase]);

  const saveReview = async (action: ReviewAction): Promise<boolean> => {
    if (!item || savingAction) return false;
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return false;
    }
    if (action === 'CORRECT_GRADE' && grade === '') {
      setError('Choose a final DR grade before saving a correction.');
      return false;
    }
    setSavingAction(action);
    setDefaultReviewer(useAsDefault ? reviewer : '');
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
      setSuccess(`${action === 'ACCEPT' ? 'DR grade confirmed from the AI suggestion' : action === 'CORRECT_GRADE' ? 'DR grade confirmed' : 'Case escalated'} for ${saved.display_name}.`);
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      setSavingAction(null);
    }
  };

  const submitDecisionAndNext = async (nextId: string | null) => {
    if (!item) return;
    const action: ReviewAction = decision === 'SENIOR_REVIEW'
      ? 'ESCALATE'
      : item.global?.grade === Number(grade) ? 'ACCEPT' : 'CORRECT_GRADE';
    const saved = await saveReview(action);
    if (saved) navigate(nextId ? `/clinician-review/${encodeURIComponent(nextId)}` : '/worklist');
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
        actions={<HStack><Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} leftIcon={<ArrowLeft size={15} />}>Back to Review</Button><Button as={Link} to="/worklist">Back to Worklist</Button></HStack>}
      />
      <Stack spacing={3} mb={5}>
        <CaseNavigation
          imageId={item.image_id}
          routePrefix="clinician-review"
          onSaveAndNext={(nextId) => { void submitDecisionAndNext(nextId); }}
          saveAndNextLabel={decision === 'FINAL_GRADE' ? 'Confirm final DR grade & next' : 'Send for senior review & next'}
          saveAtEndLabel={decision === 'FINAL_GRADE' ? 'Confirm final DR grade' : 'Send for senior review'}
        />
        <NextActionHint item={item} />
      </Stack>
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.25fr) minmax(320px, 0.75fr)' }} gap={5} alignItems="start" minW={0}>
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
        <Stack spacing={5} minW={0}>
          <Section title="Clinician decision" description="Choose one outcome for this case.">
            <Stack spacing={4}>
              <ReviewerField id="clinician-reviewer-name" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
              <Text fontSize="sm" color="text.secondary">AI suggestion: {item.global?.grade == null ? 'Not available' : `Grade ${item.global.grade}`}</Text>
              <RadioGroup value={decision} onChange={(value) => setDecision(value as ReviewDecision)}>
                <Stack spacing={3}>
                  <Box>
                    <Radio value="FINAL_GRADE">Confirm final DR grade</Radio>
                    <Text ml={6} fontSize="sm" color="text.secondary">Use when this DR grade is your final decision for this case.</Text>
                  </Box>
                  <Box>
                    <Radio value="SENIOR_REVIEW">Send for senior review</Radio>
                    <Text ml={6} fontSize="sm" color="text.secondary">Use when another clinician should review the case before final sign-off.</Text>
                  </Box>
                </Stack>
              </RadioGroup>
              {decision === 'FINAL_GRADE' && (
                <FormControl>
                  <FormLabel htmlFor="clinician-review-grade">Final DR grade</FormLabel>
                  <Select id="clinician-review-grade" value={grade} onChange={(event) => setGrade(event.target.value)} placeholder="Select grade 0-4">
                    {[0, 1, 2, 3, 4].map((value) => <option key={value} value={value}>Grade {value}</option>)}
                  </Select>
                </FormControl>
              )}
              <FormControl>
                <FormLabel htmlFor="clinician-review-remark">Remark</FormLabel>
                <Textarea id="clinician-review-remark" value={remark} onChange={(event) => setRemark(event.target.value)} placeholder="Add a review remark" rows={5} />
              </FormControl>
              {error && <Alert status="error"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
              {success && <Alert status="success"><AlertIcon /><Text fontSize="sm">{success}</Text></Alert>}
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
