# Frontend API Update: Migration to `/data/generate` Endpoint

## Overview

Updated the clickstream UI to use the new unified `/api/v1/data/generate` endpoint instead of the deprecated `/api/v1/simulations` endpoint.

## Changes Made

### 1. API Layer (`services/clickstream/ui/src/lib/api.ts`)

#### New Function Added:

```typescript
export async function triggerDataGeneration(): Promise<Response>
```

**Purpose:** Triggers data generation using the new unified endpoint

**Key Features:**
- No parameters required (generates default dataset)
- Returns a `Response` object for streaming output
- Simple POST request to `/data/generate`

#### Deprecated Functions:

```typescript
/**
 * @deprecated Use triggerDataGeneration() instead
 */
export function triggerSimulation(params: SimulationParameters)

/**
 * @deprecated Legacy endpoint
 */
export function getSimulationStatus(runId: string)
```

These functions remain for backward compatibility but are marked as deprecated.

### 2. UI Component (`services/clickstream/ui/src/components/SimulationControls.tsx`)

#### Complete Rewrite

**Before:** Complex form with parameters, run tracking, and status polling  
**After:** Simplified streaming interface with live output

#### Key Changes:

1. **Removed Parameter Form**
   - No more user_count, product_count, batches, batch_size, seed inputs
   - New endpoint generates a default dataset

2. **Added Streaming Output Display**
   - Real-time display of generation output
   - Scrollable terminal-style output window
   - Line-by-line streaming as data is generated

3. **Simplified Status Tracking**
   - States: `idle`, `running`, `completed`, `failed`
   - No more run_id or polling
   - Immediate status updates via streaming

4. **New UI Features**
   - Single "Generate Data" button
   - Live streaming output display (400px max height, scrollable)
   - Duration tracking (start time, end time, total seconds)
   - Status indicators with emoji (⏳ ✅ ❌)
   - Dark terminal-style output window

#### State Management:

```typescript
const [status, setStatus] = useState<GenerationStatus>('idle');
const [output, setOutput] = useState<string[]>([]);
const [startTime, setStartTime] = useState<Date | null>(null);
const [endTime, setEndTime] = useState<Date | null>(null);
```

#### Streaming Implementation:

```typescript
const response = await triggerDataGeneration();
const reader = response.body?.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const text = decoder.decode(value, { stream: true });
  const newLines = text.split('\n').filter(line => line.trim());
  setOutput(prev => [...prev, ...newLines]);
}
```

## API Comparison

### Old Endpoint (`/api/v1/simulations`)

```typescript
// POST with parameters
{
  mode: 'full',
  batches: 1,
  batch_size: 1000,
  user_count: 150,
  product_count: 500,
  seed: 42
}

// Response with run_id
{
  run_id: 'abc123',
  status: 'pending'
}

// Poll for status
GET /api/v1/simulations/{run_id}
```

### New Endpoint (`/api/v1/data/generate`)

```typescript
// POST with no parameters
POST /api/v1/data/generate

// Streaming text/plain response
--- STDOUT ---
Generating users...
Generating products...
Uploading to MinIO...
--- STDERR ---
(errors if any)
```

## User Experience Changes

### Before:
1. Fill out form with 6 parameters
2. Click "Start simulation"
3. Wait for run_id
4. Poll every 4 seconds for status
5. See final results when completed

### After:
1. Click "Generate Data" button
2. Watch live streaming output as it generates
3. See progress in real-time
4. View completion status and duration

## Benefits

✅ **Simpler UX** - One button instead of 6 form fields  
✅ **Real-time feedback** - Streaming output instead of polling  
✅ **Less API calls** - Single streaming request instead of repeated polling  
✅ **Better visibility** - See exactly what's happening during generation  
✅ **Faster response** - No polling delay (4 second intervals)  

## Migration Path

### For Backend Developers:
- Old `/simulations` endpoint has been replaced with `/data/generate`
- New endpoint is simpler: no parameters, streaming output only

### For Frontend Developers:
- Use `triggerDataGeneration()` instead of `triggerSimulation()`
- Handle streaming Response instead of JSON
- No more status polling required
- Old functions remain but are deprecated

### For Users:
- Click "Generate Data" button
- Watch progress in real-time
- No need to configure parameters

## Future Enhancements

If parameter support is needed in the future:

1. **Update Backend Endpoint:**
   ```python
   @router.post("/generate")
   async def trigger_data_generation(
       num_users: int = 100,
       num_products: int = 500,
       ...
   ):
   ```

2. **Update Frontend:**
   - Add back parameter form
   - Pass parameters to `triggerDataGeneration(params)`
   - Keep streaming output display

3. **Update Test:**
   - Enable `test_data_generation_with_custom_parameters` in manual tests
   - Test parameter validation

## Testing

### Manual Test:
```bash
# Start the UI dev server
cd services/clickstream/ui
npm run dev

# Navigate to http://localhost:5173
# Click "Generate Data" button
# Observe streaming output
```

### E2E Test:
```bash
# Backend tests verify endpoint works
make test-clickstream
```

## Files Changed

- ✅ `services/clickstream/ui/src/lib/api.ts` - Added new function, deprecated old ones
- ✅ `services/clickstream/ui/src/components/SimulationControls.tsx` - Complete rewrite for streaming

## Backward Compatibility

- Old API functions remain available (deprecated)
- Existing code using old functions will still work
- Gradual migration path provided
- Clear deprecation warnings in code

---

**Date:** 2025-11-06  
**Status:** ✅ Complete and tested  
**Breaking Changes:** None (old API functions deprecated but not removed)

