#!/usr/bin/env python3
"""
Check cost, usage, and timing for a completed Claude batch job
Usage: python check_batch_cost.py <batch_id>
"""
import os
import sys
from anthropic import Anthropic
from datetime import datetime, timezone

def check_batch_cost(batch_id: str):
    client = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
    # Get batch info
    batch = client.messages.batches.retrieve(batch_id)
    
    # Get batch results
    results = list(client.messages.batches.results(batch_id))
    
    # Calculate total usage
    total_input = 0
    total_output = 0
    succeeded = 0
    errored = 0
    
    for result in results:
        result_dict = result.model_dump()
        if result_dict['result']['type'] == 'succeeded':
            message = result_dict['result']['message']
            usage = message.get('usage', {})
            total_input += usage.get('input_tokens', 0)
            total_output += usage.get('output_tokens', 0)
            succeeded += 1
        else:
            errored += 1
    
    # Calculate costs (batch pricing - 50% off)
    # Claude Sonnet 4.5: $1.50/MTok input, $7.50/MTok output
    input_cost = (total_input / 1_000_000) * 1.50
    output_cost = (total_output / 1_000_000) * 7.50
    total_cost = input_cost + output_cost
    
    # Calculate timing
    created_at = batch.created_at
    ended_at = batch.ended_at
    
    # Handle datetime conversion if needed
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    if isinstance(ended_at, str):
        ended_at = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
    
    duration = None
    if ended_at:
        duration = ended_at - created_at
        duration_minutes = duration.total_seconds() / 60
        duration_hours = duration_minutes / 60
    
    print('=' * 60)
    print('BATCH PROCESSING SUMMARY')
    print('=' * 60)
    print(f'Batch ID: {batch_id}')
    print(f'Status: {batch.processing_status}')
    print()
    
    # Timing information
    print('TIMING:')
    print(f'Started:  {created_at.strftime("%Y-%m-%d %H:%M:%S")}')
    if ended_at:
        print(f'Ended:    {ended_at.strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'Duration: {int(duration_hours)}h {int(duration_minutes % 60)}m ({duration_minutes:.1f} minutes)')
    print()
    
    # Document counts
    print('DOCUMENTS:')
    print(f'Processed: {succeeded}')
    print(f'Failed:    {errored}')
    if succeeded > 0 and duration:
        print(f'Rate:      {succeeded/duration_minutes:.1f} docs/minute')
    print()
    
    # Token usage
    print('TOKEN USAGE:')
    print(f'Input:     {total_input:,} tokens')
    print(f'Output:    {total_output:,} tokens')
    print(f'Total:     {total_input + total_output:,} tokens')
    if succeeded > 0:
        print(f'Avg/doc:   {(total_input + total_output)/succeeded:,.0f} tokens')
    print()
    
    # Cost breakdown
    print('COST (Batch API - 50% discount):')
    print(f'Input:     ${input_cost:.4f}')
    print(f'Output:    ${output_cost:.4f}')
    print(f'Total:     ${total_cost:.4f}')
    if succeeded > 0:
        print(f'Per doc:   ${total_cost/succeeded:.4f}')
    print()
    
    print('Model: claude-sonnet-4-5-20250929')
    print('Pricing: $1.50/MTok input, $7.50/MTok output (batch discount applied)')
    print('=' * 60)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <batch_id>")
        sys.exit(1)
    
    check_batch_cost(sys.argv[1])
