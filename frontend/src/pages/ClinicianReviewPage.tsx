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
import { ArrowLeft, Pencil } from '@/lib/icons';
import { getDefaultReviewer, setDefaultReviewer } from '@/lib/reviewerPreference';
import { ReviewerField } from '@/components/common/ReviewerField';
import { CaseNavigation } from '@/components/common/CaseNavigation';
import { NextActionHint } from '@/components/common/NextActionHint';

type ReviewAction = 'ACCEPT' | 'CORRECT_GRADE';

function errorText(err: unknown) {
  return err instanceof Error ? err.message : 'The request could not be completed.';
}

function reviewLabel(item: CaseRecord) {
  if (item.state === 'ESCALATED') return 'Legacy senior-review record';
  if (item.clinician_review?.final_grade !== null && item.clinician_review?.final_grade !== undefined) return 'Grading complete';
  if (item.state === 'NEEDS_CORRECTION') return 'Needs correction';
  return 'Not confirmed';
}

export function ClinicianReviewPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { imageId } = useParams<{ imageId: string }>();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [reviewer, setReviewer] = useState(() => getDefaultReviewer());
  const [useAsDefault, setUseAsDefault] = useState(() => Boolean(getDefaultReviewer()));
  const [grade, setGrade] = useState('');
  const [remark, setRemark] = useState('');
  const [editingConfirmed, setEditingConfirmed] = useState(false);
  const [navigationAccepted, setNavigationAccepted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCase = useCallback(async () => {
    if (!imageId) return;
    setLoading(true);
    setError(null);
    try {
      const loaded = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(imageId)}`);
      setItem(loaded);
      setReviewer(loaded.clinician_review?.reviewer ?? getDefaultReviewer());
      setUseAsDefault(Boolean(getDefaultReviewer()));
      setRemark(loaded.clinician_review?.remark ?? '');
      setGrade(loaded.clinician_review?.final_grade == null ? '' : String(loaded.clinician_review.final_grade));
      setEditingConfirmed(false);
      setNavigationAccepted(false);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [imageId]);

  useEffect(() => { void loadCase(); }, [loadCase]);

  const confirmed = item?.clinician_review?.final_grade !== null && item?.clinician_review?.final_grade !== undefined;
  const readOnly = Boolean(confirmed && !editingConfirmed);

  const confirmLeave = () => {
    if (navigationAccepted || confirmed && !editingConfirmed) return true;
    const accepted = window.confirm('You are still working on this image. Switch image and keep this case unconfirmed?');
    if (accepted) setNavigationAccepted(true);
    return accepted;
  };

  const beginGradeEdit = () => {
    if (!confirmed || editingConfirmed) return;
    if (window.confirm('Edit confirmed DR grade?\n\nThis grade has already been confirmed. Continuing will reopen the grading step and create a new review revision.')) {
      setEditingConfirmed(true);
      setNavigationAccepted(false);
    }
  };

  const saveGrade = async () => {
    if (!item || saving) return;
    if (!reviewer.trim()) {
      setError('Reviewer name is required.');
      return;
    }
    if (grade === '') {
      setError('Choose a final DR grade before confirming.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const action: ReviewAction = !confirmed && item.global?.grade === Number(grade) ? 'ACCEPT' : 'CORRECT_GRADE';
      const saved = await apiJson<CaseRecord>(`/v1/cases/${encodeURIComponent(item.image_id)}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          revision: item.revision,
          action,
          reviewer: reviewer.trim(),
          grade: Number(grade),
          comment: remark,
        }),
      });
      setDefaultReviewer(useAsDefault ? reviewer : '');
      setItem(saved);
      navigate(`/edit/${encodeURIComponent(saved.image_id)}`, { state: { gradingComplete: true } });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
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
        actions={<HStack><Button as={Link} to={`/review/${encodeURIComponent(item.image_id)}`} leftIcon={<ArrowLeft size={15} />} onClick={(event) => { if (!confirmLeave()) event.preventDefault(); }}>Back to Review</Button><Button as={Link} to="/worklist" onClick={(event) => { if (!confirmLeave()) event.preventDefault(); }}>Back to Worklist</Button></HStack>}
      />
      <Stack spacing={3} mb={5}>
        <CaseNavigation
          imageId={item.image_id}
          routePrefix="clinician-review"
          incomplete={!confirmed || editingConfirmed}
          onBeforeNavigate={confirmLeave}
        />
        <NextActionHint item={item} />
      </Stack>
      <Grid templateColumns={{ base: '1fr', laptop: 'minmax(0, 1.25fr) minmax(320px, 0.75fr)' }} gap={5} alignItems="start" minW={0}>
        <Section title="Review summary" description="AI output is optional evidence; this page records the clinician's final grade.">
          <RetinalCanvas item={item} showAi={false} showHuman={true} />
          <SimpleGrid columns={{ base: 1, tablet: 3 }} spacing={4} mt={4}>
            <Stack spacing={1}><Text fontSize="sm" color="text.secondary">AI-predicted grade</Text><Heading size="md">{item.global?.grade == null ? 'Not analyzed' : `Grade ${item.global.grade}`}</Heading></Stack>
            <Stack spacing={1}><Text fontSize="sm" color="text.secondary">Human annotations</Text><Heading size="md">{item.human_annotations?.length ?? 0}</Heading></Stack>
            <Stack spacing={1}><Text fontSize="sm" color="text.secondary">AI lesion suggestions</Text><Heading size="md">{item.lesion_review?.suggestion_count ?? 0}</Heading></Stack>
          </SimpleGrid>
          <HStack mt={4} justify="space-between" align="center" borderTopWidth="1px" borderColor="border.subtle" pt={4}>
            <Text color="text.secondary">Grading status</Text>
            <Text fontWeight="semibold">{reviewLabel(item)}</Text>
          </HStack>
          {item.clinician_review && <Text mt={3} fontSize="sm" color="text.secondary">Confirmed by {item.clinician_review.reviewer} - {new Date(item.clinician_review.timestamp).toLocaleString()}</Text>}
        </Section>
        <Stack spacing={5} minW={0}>
          {readOnly ? (
            <Section title="Grading complete" description="The confirmed grade is read-only until you explicitly reopen this edit session.">
              <Stack spacing={3}>
                <Text><strong>DR grade:</strong> Grade {item.clinician_review?.final_grade}</Text>
                <Text fontSize="sm" color="text.secondary">Reviewer: {item.clinician_review?.reviewer}</Text>
                <Button leftIcon={<Pencil size={15} />} variant="outline" onClick={beginGradeEdit}>Edit confirmed grade</Button>
              </Stack>
            </Section>
          ) : (
            <Section title="Clinician decision" description="Select one final DR grade, then continue to annotation review.">
              <Stack spacing={4}>
                <ReviewerField id="clinician-reviewer-name" value={reviewer} useAsDefault={useAsDefault} onChange={setReviewer} onUseAsDefaultChange={setUseAsDefault} />
                <Text fontSize="sm" color="text.secondary">AI suggestion: {item.global?.grade == null ? 'Not available' : `Grade ${item.global.grade}`}</Text>
                <FormControl>
                  <FormLabel htmlFor="clinician-review-grade">Final DR grade</FormLabel>
                  <Select id="clinician-review-grade" value={grade} onChange={(event) => setGrade(event.target.value)} placeholder="Select grade 0-4">
                    {[0, 1, 2, 3, 4].map((value) => <option key={value} value={value}>Grade {value}</option>)}
                  </Select>
                </FormControl>
                <FormControl>
                  <FormLabel htmlFor="clinician-review-remark">Remark</FormLabel>
                  <Textarea id="clinician-review-remark" value={remark} onChange={(event) => setRemark(event.target.value)} placeholder="Add a review remark" rows={5} />
                </FormControl>
                {error && <Alert status="error"><AlertIcon /><Text fontSize="sm">{error}</Text></Alert>}
                <Button variant="solid" onClick={() => void saveGrade()} isLoading={saving}>Confirm DR Grade</Button>
                {confirmed && <Text fontSize="sm" color="text.secondary">This finalizes the grade and continues to annotation review.</Text>}
              </Stack>
            </Section>
          )}
          <Section title="Review record" description="Persisted in the existing case store with revision history.">
            {item.clinician_review ? (
              <Stack spacing={2} fontSize="sm">
                <Text><strong>Final grade:</strong> {item.clinician_review.final_grade == null ? 'Not set' : item.clinician_review.final_grade}</Text>
                <Text><strong>Remark:</strong> {item.clinician_review.remark || 'None'}</Text>
                <Text fontSize="xs" color="text.muted">Revision {item.clinician_review.revision}</Text>
              </Stack>
            ) : <Text color="text.secondary">Not confirmed.</Text>}
          </Section>
        </Stack>
      </Grid>
    </Box>
  );
}
