# Source excerpt. Imports and other methods are omitted.

def _initial_open_request(prompt, role, public_guard, *, rates, definitions,
        instructions, response_format, final_instructions, role_slot, source_commit,
        memory_max_turns=None, memory_first_tool_free_turn=None):
    """Shared original initial envelope; no directory, tool or transport write.

    Live roles and the finite pre-owner public count use this same constructor.
    Legacy roles keep their original unprojected envelope. A public guard must
    have been obtained through the exact original live/read-only context.
    """
    if memory_max_turns is not None or memory_first_tool_free_turn is not None:
        if not final_instructions.startswith(instructions):
            raise ValueError('Final instructions must extend the same original role instructions')
        suffix = final_instructions[len(instructions):]
        instructions += _memory_turn_notice(memory_max_turns, memory_first_tool_free_turn)
        final_instructions = instructions+suffix
    frozen = deepcopy(prompt)
    if public_guard is not None:
        frozen = public_guard.project_prompt(frozen)
    content, policy = _initial_user_json(frozen, role)
    expected = dict(model=rates['api_model'],reasoning={'effort':rates['effort']},
        instructions=instructions,tools=deepcopy(definitions),tool_choice='auto',
        parallel_tool_calls=False,text={'format':deepcopy(response_format)})
    request = dict(expected,input=[dict(role='user',content=content)])
    if public_guard is not None:
        public_guard.bind_request(content,expected,final_instructions,
            role_slot=role_slot,source_commit=source_commit,
            **({'memory_completion_turn':memory_first_tool_free_turn-1}
               if memory_first_tool_free_turn is not None and memory_first_tool_free_turn >= 3 else {}))
        public_guard.validate_request(request)
    return frozen, content, policy, request


class _OpenRole:
    def _run_open(self, prompt, slot, instructions, response_format, decode, artifact, status,
                  *, delivery_repair=False, normal_delivery_repair=False):
        if getattr(getattr(self.broker,'research_memory_session',None),'initial_count_only',False):
            from earnings_population_memory_history import PublicMemoryFailure
            raise PublicMemoryFailure('Read-only initial count cannot become a live role invocation')
        if self.controller_min_headroom is not None and (
                response_format.get('name') != 'earnings_population_decision_v1'
                or self.role != 'controller'):
            raise ValueError('Controller headroom requires the original population decision schema')
        if (type(normal_delivery_repair) is not bool or normal_delivery_repair
                and (delivery_repair is not False or self.role != 'author')):
            raise ValueError('Normal same-slot correction is a distinct explicit Author option')
        if type(delivery_repair) is not bool or delivery_repair and self.role != 'author':
            raise ValueError('Delivery repair is explicit Author-only engineering')
        self._context()
        frozen = deepcopy(prompt)
        ctx, output = self.context, Path(slot)
        if (str(output) not in ctx['slots'] or not output.is_absolute() or output.resolve() != output):
            raise ValueError('Open role outside exact declared slot')
        limits = ctx['limits']
        cutoff = getattr(self.budget,'monotonic_deadline',ctx['cutoff_monotonic'])
        if type(cutoff) not in (int,float) or not math.isfinite(cutoff) or cutoff < 0:
            raise ValueError('Finite original budget cutoff required')
        hard = min(ctx['cutoff_monotonic'],cutoff,time.monotonic()+limits['wall_seconds'])
        if time.time() >= utc_epoch(ctx['cutoff_utc']) or time.monotonic() >= hard:
            raise BudgetStop('Open-role cutoff before factory')
        if output.exists() or output.is_symlink():
            raise FileExistsError('Consumed open-role slot remains closed to retry')
        self.budget.active()
        output.mkdir(parents=True,exist_ok=False)
        identity = (output.stat().st_dev,output.stat().st_ino)
        protected = {}
        def capture():
            for path in output.iterdir():
                if path.resolve() != path or not path.is_file():
                    raise ValueError('Nonregular open-role artifact')
                token = e.digest(path.read_bytes())
                if path in protected and protected[path] != token:
                    raise ValueError('Preserved open-role artifact changed during send')
                protected[path] = token
        def timely(*, check_budget=True):
            self._context()
            if (output.resolve() != output or (output.stat().st_dev,output.stat().st_ino) != identity
                    or self.broker.definitions != self.definitions):
                raise ValueError('Open-role output or broker drift')
            for path, token in protected.items():
                if path.resolve() != path or not path.is_file() or e.digest(path.read_bytes()) != token:
                    raise ValueError('Preserved open-role artifact drift')
            if time.time() >= utc_epoch(ctx['cutoff_utc']) or time.monotonic() >= hard:
                raise BudgetStop('Open-role original deadline reached')
            if check_budget:
                self.budget.active()
        reader = getattr(type(self.broker), 'external_memory_guard', None)
        public_guard = reader(self.broker) if callable(reader) else None
        request_validator=public_guard.validate_request if public_guard is not None else None
        from earnings_population_independent_q12 import selected as q12_selected
        if self.role=='review' and q12_selected(getattr(self,'review_runtime',None)):
            from earnings_population_q12_public import check_request
            if request_validator is not None:
                raise ValueError('Q12 Review must use the original independent review boundary')
            request_validator=check_request
        first_tool_free = max(1, self.max_turns-2) if delivery_repair or normal_delivery_repair else self.max_turns
        memory_schedule = (dict(memory_max_turns=self.max_turns, memory_first_tool_free_turn=first_tool_free)
            if {'research_memory','record_research_memory'} <= {row['name'] for row in self.definitions} else {})
        frozen, initial_content, initial_policy, initial_request = _initial_open_request(
            frozen,self.role,public_guard,rates=ctx['rates'],definitions=self.definitions,
            instructions=instructions,response_format=response_format,
            final_instructions=instructions+FINALIZE+self._final_instruction(),
            role_slot=output,source_commit=ctx['source_commit'],**memory_schedule)
        instructions = initial_request['instructions']
        if public_guard is not None:
            # Local canonical guards have already run. Retain their complete
            # input locally; only the shared positive envelope may be sent.
            e.durable_json(output/'local-canonical-input.json',public_guard.local_prompt)
        e.durable_json(output/'identity.json',{'context':self.binding,'source_commit':ctx['source_commit'],
            'evidence_scope':'source-bound open research transport; not empirical improvement',
            'model_authorship_verified':False,'max_turns':self.max_turns,'max_tool_calls':self.max_tool_calls,
            **({'normal_delivery_policy':'earnings_normal_same_slot_delivery_v1',
                'cross_id_continuation_allowed':False} if normal_delivery_repair else {}),
            **({'initial_user_serialization': initial_policy} if initial_policy else {})})
        e.durable_json(output/'effective-input.json',frozen)
        capture()
        history = [{'role':'user','content':initial_content}]
        review_handoff = (self.role == 'review'
            and response_format.get('name') == 'earnings_population_review_v1')
        failure, chosen, last_response = None, None, None
        memory_failure_state = None
        correcting = False
        seen, tool_calls, turn = set(), 0, 0
        started = time.monotonic()
        try:
            timely()
            # The original owner verifies the exact in-flight reservation on
            # generation sends. active() here would reject our own reservation.
            client=self.factory()
            if self.socket_timeout_seconds is not None:
                client.timeout=self.socket_timeout_seconds
            transport = _CapacityDeadlineHTTP(client,lambda:timely(check_budget=False),deadline_utc=ctx['cutoff_utc'],
                rollout_seconds=limits['wall_seconds'],captured_deadline=hard)
            with e.absolute_window(hard-time.monotonic()):
                for turn in range(1,self.max_turns+1):
                    timely()
                    # Reserve the final two ORIGINAL turns for mechanical
                    # correction. No new slot, model, clock or request ceiling.
                    final = (normal_delivery_repair and correcting or turn >= first_tool_free)
                    memory_reader = getattr(type(self.broker), 'research_memory_final_ready', None)
                    memory_ready = memory_reader(self.broker) if callable(memory_reader) else True
                    if type(memory_ready) is not bool:
                        raise ValueError('Exact mandatory-memory completion state required')
                    if final and not memory_ready:
                        # LOCAL booleans only, after refusal. Never send this
                        # diagnostic, inspect private history or substitute it
                        # for the original durable readiness/acceptance gates.
                        try:
                            diagnostic = getattr(type(self.broker), 'research_memory_control_state', None)
                            if callable(diagnostic):
                                state = diagnostic(self.broker)
                                if (type(state) is dict and set(state) == {
                                        'required','search_ack_in_memory','delta_committed_in_memory',
                                        'action_pending_in_memory','poisoned_in_memory'}
                                        and all(type(value) is bool for value in state.values())):
                                    memory_failure_state = dict(state)
                        except BaseException:
                            pass  # This optional diagnostic cannot replace the original refusal.
                        raise BudgetStop('Mandatory memory is incomplete at the original final turn; no final generation')
                    request = deepcopy(initial_request)
                    outgoing_history = deepcopy(history)
                    if public_guard is not None:
                        outgoing_history = public_guard.provider_history(outgoing_history)
                    request.update(input=outgoing_history,
                        instructions=instructions+(FINALIZE+self._final_instruction() if final else ''),
                        tool_choice='none' if final else 'auto')
                    if (self.role=='controller' and turn==8 and final and memory_ready
                            and public_guard is not None and public_guard.omit_q12_final_tool_declarations()):
                        request['tools']=[]
                    if (public_guard is not None and memory_schedule and not final and not memory_ready
                            and first_tool_free >= 3 and turn == first_tool_free-1):
                        # Consume the last ORIGINAL tool-enabled generation,
                        # not a retry or new turn. The model writes the delta;
                        # all original acceptance and final guards still run.
                        choice = public_guard.memory_completion_choice(turn)
                        if choice is None:
                            raise BudgetStop('Original memory state cannot use the reserved delta opportunity')
                        request['tool_choice'] = choice
                    completion=({**request,'tool_choice':'none',
                        'instructions':instructions+FINALIZE+self._final_instruction()}
                        if (self.role=='author' or review_handoff) and not final and memory_ready else None)
                    controller_completion = ({**request, 'tool_choice': 'none',
                        'instructions': instructions+FINALIZE+self._final_instruction()}
                        if self.controller_min_headroom is not None and not final and memory_ready else None)
                    citations=(public_guard.precommit_citation_handles()
                        if self.role=='controller' and not final and not memory_ready
                        and public_guard is not None else None)
                    packed=pack(e.ReceiptHTTP(transport,output),request,limits,output,turn,
                        author_final=self.role=='author' and final,completion_request=completion,
                        review_final=review_handoff and final,
                        controller_public_final=(self.role=='controller' and final and turn==8
                            and memory_ready and public_guard is not None
                            and not public_guard.controller_bounded_enabled()
                            and public_guard.controller_final_enabled()),
                        controller_bounded_context=(public_guard.controller_bounded_context()
                            if self.role=='controller' and final and turn==8 and memory_ready
                            and public_guard is not None and public_guard.controller_bounded_enabled() else None),
                        controller_precommit_context=(public_guard.controller_precommit_context()
                            if self.role=='controller' and not final and turn==7 and not memory_ready
                            and public_guard is not None and public_guard.controller_precommit_enabled() else None),
                        prepared_count_context=self.binding,
                        **({'citation_handles':citations} if citations is not None else {}),
                        **({'request_validator':request_validator} if request_validator is not None else {}),
                        **({'controller_completion_request': controller_completion,
                            'controller_min_headroom': self.controller_min_headroom}
                            if controller_completion is not None else {}))
                    request,prepared_count=packed if type(packed) is tuple else (packed,None)
                    if request_validator is not None:
                        request_validator(request)  # Read-only; never alter PreparedCount input.
                    final=final or request['tool_choice']=='none'
                    capture(); timely()
                    budgeted_response(e.ReceiptHTTP(transport,output),request,ctx['rates'],limits,self.budget,output,turn,
                        **({} if prepared_count is None else {'prepared_count':prepared_count}))
                    last_response = output/f'{turn:02d}-response.json'
                    original = e.strict_json(last_response.read_text())
                    capture(); timely()
                    items = original.get('output')
                    if (type(items) is not list or any(type(item) is not dict
                            or item.get('type') not in {'reasoning','message','function_call'} for item in items)):
                        raise ValueError('Unsupported open-role response item')
                    calls = [item for item in items if item['type']=='function_call']
                    if request['tool_choice'] == {'type':'function','name':'record_research_memory'} and (
                            len(calls) != 1 or calls[0].get('name') != 'record_research_memory'):
                        raise BudgetStop('Reserved memory generation did not return exactly its required delta call')
                    if public_guard is not None:
                        public_guard.provider_items(items)
                    if normal_delivery_repair:
                        if original.get('refusal') is not None or any(
                                item.get('refusal') is not None or
                                type(item.get('content')) is list and any(type(part) is dict
                                    and (part.get('type') == 'refusal' or part.get('refusal') is not None)
                                    for part in item['content']) for item in items):
                            raise ValueError('Normal delivery refusal is not mechanically repairable')
                        truncated = (not calls and original.get('status') == 'incomplete'
                            and original.get('error') is None
                            and type(original.get('incomplete_details')) is dict
                            and original['incomplete_details'].get('reason') == 'max_output_tokens')
                        if not truncated and (original.get('status') != 'completed'
                                or original.get('error') is not None
                                or original.get('incomplete_details') is not None
                                or any(item.get('status') not in (None, 'completed') for item in items)):
                            raise ValueError('Normal delivery provider uncertainty is not mechanically repairable')
                    if not calls:
                        try:
                            chosen = decode(original)
                        except DeliveryError as error:
                            if normal_delivery_repair and error.feedback.get('schema') != 'earnings_normal_same_slot_delivery_v1':
                                raise ValueError('Normal correction cannot consume named repair authority') from error
                            if not (delivery_repair or normal_delivery_repair) or turn == self.max_turns:
                                raise
                            timely()
                            correcting = True
                            record = deepcopy(error.feedback)
                            record.update(response={'path':str(last_response),
                                'sha256':e.digest(last_response.read_bytes())},
                                public_draft_sha256=digest(error.public_draft),
                                turn=turn, remaining_original_turns=self.max_turns-turn,
                                new_technical_attempt=False, new_scientific_child=False)
                            e.durable_json(output/f'{turn:02d}-delivery-feedback.json', record)
                            capture(); timely()
                            # Do not replay hidden reasoning/private continuity.
                            # Restart from the frozen public input and ONLY the
                            # model's own public draft plus bounded actual error.
                            history = [{'role':'user','content':initial_content},
                                {'role':'user','content':json.dumps(dict(
                                    technical_delivery_feedback=record,
                                    public_draft=error.public_draft,
                                    instruction='Correct this mechanical delivery of the SAME frozen decision. '
                                    'Return a complete literal patch and CASES within unchanged limits; '
                                    'do not change parent, decision or hypothesis.'),
                                    sort_keys=True,ensure_ascii=normal_delivery_repair,allow_nan=False)}]
                            if public_guard is not None:
                                public_guard.correction(history[1]['content'])
                            continue
                        break
                    if final:
                        raise ValueError('Final open-role turn attempted tools')
                    if tool_calls+len(calls) > self.max_tool_calls:
                        raise ValueError('Open-role tool budget exhausted')
                    ids = [call.get('call_id') for call in calls]
                    if (any(type(token) is not str or not 1<=len(token)<=200 or token in seen for token in ids)
                            or len(set(ids)) != len(ids)):
                        raise ValueError('Missing or duplicate function-call identity')
                    seen.update(ids); history.extend(deepcopy(items))
                    for call in calls:
                        timely(); tool_calls += 1
                        try:
                            if (type(call.get('arguments')) is not str or len(call['arguments'].encode())>65536
                                    or type(call.get('name')) is not str):
                                raise ValueError('Bounded named tool arguments required')
                            args = e.strict_json(call['arguments'])
                            if type(args) is not dict:
                                raise ValueError('Exact object tool arguments required')
                            spec = next((item for item in self.definitions if item['name']==call['name']),None)
                            if spec is None:
                                raise ValueError('Unregistered broker tool')
                            arguments(args,spec['parameters'])
                            if public_guard is not None:
                                public_guard.begin_current_call(call['call_id'],call['name'],args)
                            result = self.broker.dispatch(call['name'],args)
                            rendered = json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False)
                            if len(rendered.encode()) > 131072:
                                raise ValueError('Open-role tool observation exceeds bound')
                            if public_guard is not None:
                                public_guard.admit_output(call['call_id'],call['name'],rendered)
                        except (ValueError,TypeError,KeyError,ArithmeticError,SyntaxError) as error:
                            if any(base.__name__=='BudgetStop' for base in type(error).__mro__):
                                raise  # Financial stops outrank an ordinary public tool rejection.
                            rendered = (public_guard.admit_error(call['call_id'],call.get('name'),type(error).__name__)
                                if public_guard is not None else json.dumps({
                                    'error':'Tool request rejected; original failure retained by broker when dispatched.',
                                    'error_type':type(error).__name__},sort_keys=True))
                        timely()
                        observed = {'type':'function_call_output','call_id':call['call_id'],'output':rendered}
                        e.durable_json(output/f"{turn:02d}-tool-{raw_digest(call['call_id'].encode())[:12]}.json",observed)
                        history.append(observed); capture()
                if chosen is None:
                    raise RuntimeError('Open-role ended without a final business object')
            timely()
        except BaseException as error:
            failure = error
        finally:
            try:
                captured = sorted(output.glob('[0-9][0-9]-response.json'))
                if captured:
                    last_response = captured[-1]
                    save_bytes(output/'response.json',last_response.read_bytes())
                e.durable_json(output/'budget-summary.json',self.budget.summary())
            except BaseException as error:
                failure = error if isinstance(failure, DeliveryError) else failure or error
        if isinstance(failure, DeliveryError):
            try:
                timely(); capture()
                record = deepcopy(failure.feedback)
                record.update(response={'path':str(output/'response.json'),
                    'sha256':e.digest((output/'response.json').read_bytes())},
                    public_draft_sha256=digest(failure.public_draft),
                    remaining_original_turns=0, new_scientific_child=False)
                e.durable_json(output/'technical-delivery-failure.json', record)
                capture()
            except BaseException as error:
                failure = error  # Unsettled fees/integrity/deadline are hard stops.
        if failure is None:
            try:
                timely()
                bound = {'path':str(output/'response.json'),'sha256':e.digest((output/'response.json').read_bytes())}
                e.durable_json(output/(artifact+'.json'),{artifact:chosen,'original':bound})
            except BaseException as error:
                failure = error
        e.durable_json(output/'result.json',{'status':status if failure is None else 'FAILED_NO_RETRY',
            'error_type':None if failure is None else type(failure).__name__,'turns':turn,'tool_calls':tool_calls,
            'wall_seconds':time.monotonic()-started,'retry_allowed':False,
            'final_numbered_response':None if last_response is None else last_response.name,
            **({'mandatory_memory_at_final_guard':memory_failure_state}
                if memory_failure_state is not None else {}),
            'evidence_scope':'Actual counted role/tool originals require independent audit','model_authorship_verified':False})
        if failure is not None:
            if not isinstance(failure,Exception):
                raise failure
            raise RuntimeError('Open research role failed once; diagnose originals before a fresh attempt: '+type(failure).__name__) from failure
        return bound
