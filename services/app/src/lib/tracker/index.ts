import Tracker from '@openreplay/tracker';

const key = Symbol('openreplay tracker');

export interface TrackerContext {
	getTracker: () => Tracker | undefined;
}

export { Tracker, key };
