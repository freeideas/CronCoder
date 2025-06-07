# Code Formatting Guidelines

## Core Philosophy

### Brevity Above All

Fewer lines of code to achieve the same result beats almost every other concern:

- **Clarity**: A few lines of code is clearer than a lot of code
- **Performance**: A few lines of code will often run faster than a lot of code
- **Optimization**: When brevity doesn't improve performance directly, it's easier to optimize a few lines than a large body of code


### Only known-needed methods

Don't write equals or hashCode or toString unless there is some reason to believe they will be needed. Similarly,
don't write any code unless there is reason to believe it will be needed.

### Prefer Early Returns and Breaks

Always make code shorter and flatter when possible instead of nesting blocks:

```java
// AVOID: Deeply nested code
public boolean processItem( Item item ) {
    if ( item != null ) {
        if ( item.isValid() ) {
            if ( item.canProcess() ) {
                // Process the item
                return true;
            }
        }
    }
    return false;
}

// BETTER: Flat code with early returns
public boolean processItem( Item item ) {
    if ( item == null ) return false;
    if ( !item.isValid() ) return false;
    if ( !item.canProcess() ) return false;

    // Process the item
    return true;
}
```

Similarly for loops:

```java
// AVOID: Nested conditions inside loops
while ( true ) {
    if ( someCondition ) {
        doSomeThings();
        doMoreThings();
    } else {
        break;
    }
}

// BETTER: Early break to flatten structure
while ( true ) {
    if ( !someCondition ) break;
    doSomeThings();
    doMoreThings();
}
```

### On Exception Handling

- Do not catch exceptions just to re-throw them
- Let runtime exceptions bubble up naturally
- Do not clutter code with unnecessary try-catch blocks
- Only catch exceptions when:
  - They need to be part of a return value
  - You're actually handling the exception in a meaningful way
  - The API requires you to catch specific checked exceptions

### On Comments

- Comments are almost always lies
  - If they aren't lies right now, they will be after changes happen; possibly even due to changes in other code files
  - Writing comments tempts developers to write code that is difficult to understand
  - If code isn't self-explanatory, improve the code rather than explaining it with comments
  - Better code usually means fewer lines of code
  - @param and @return comments are silly because these should be obvious from reading the code; comments are not meant for people who can't read code
  - It is good to have one brief comment at the top of a class or method to explain the purpose of the class or interface, and a few inspiring words about what is so great about it
  - Example of a good comment (which should include line breaks to follow the 120 character limit rule, which is mentioned in a different section below):
    ```java
    /**
     * This class expresses any part of any tree-like structure as a tree node, in an incredibly light-weight way.
     */
    ```

### On Console Output

- Perfect code doesn't log anything unless something unexpected happens
- No console prints (System.out.println, System.err.println) except where the application specifically calls for it
- Debug logs are almost always useless because it takes too much time to read them
- A deliberately minimal testing framework is used in this codebase, which consists of `jLib.Lib.testClass()`, which finds all static methods in the class whose name ends with `"_TEST_"` and return a boolean. These methods can call `Lib.asrt( some boolean condition, "a message that helps us identify which line of code failed" )` and `Lib.asrtEQ( a, b, "a message that helps us identify which line of code failed" )`. These eliminate the need for any console output for testing. These test methods should declare `throws Exception`, and not catch any exceptions, but just let them naturally bubble up to the testing framework, except of course in special cases where an exception is expected.

### On Testing Philosophy

- Tests should focus on verifying that components behave correctly with valid inputs
- Testing error handling and edge cases is usually not valuable - focus on the happy path
- A component that works correctly with proper inputs is far more important than one that gracefully handles invalid inputs
- Time spent testing error conditions is better spent making the component work better with correct inputs
- Exception: Test error conditions only when they represent important business logic or security boundaries

This document outlines the formatting guidelines for Java code.
The code examples below here are good examples of how to format your code.

## Spacing

### Blank Lines
- Use 3 blank lines:
  - Between methods or function defs
  - Before the first method and after the last method
  - Between imports and class declaration
  - EXCEPTION: anonymous inner classes have no blank lines
  - EXCEPTION: inner classes and private classes have one blank line between methods

- Use 0 blank lines:
  - Between closely related methods (same name with different args, getter/setter pairs, constructors)
  - Between a method and its test method
  - Within method bodies
  - Within inner classes

### Parentheses
- Add spaces after opening and before closing parentheses when they contain punctuation:
  - `methodName( arg1, arg2 )`
  - `if ( condition )`
  - `super( new ArrayList<>() )`
  - `equals( otherItem() )`

- Don't add spaces when parentheses have no punctuation inside:
  - `hashCode()`
  - `equals(other)`

### Operators
- No spaces around comparison operators: `a==b`, `i<10`
- Spaces around logical operators: `a==b && b==c`

### Commas
- One space after commas
- Exception: No space between key/value pairs: `Map.of( "one",1, "two",2 )`
- No space around colon in enhanced for loops: `for ( Item item:collection )`

### Special Cases
- No spaces in type definitions: `Map<String,List<Integer>>`
- No spaces in annotations: `@SuppressWarnings({"unchecked"})` and `@SuppressWarnings({"unchecked","unused"})`
- Do not add supression warnings; only format the ones that are already there, with no spaces.

## Code Structure

### Single Statement Blocks
- For single statement blocks, put statement on same line as control structure
- Don't use braces for single statement blocks (except try/catch/finally)
```java
if ( condition ) return;
while ( condition ) callMethod();
for ( int i=0; i<10; i++ ) callMethod();
```

### Methods
- Methods with single-line bodies should be on same line as signature:
```java
public void methodName() { callMethod(); }
```

### try/catch/finally blocks
- try/catch/finally with single statement bodies should be on same line as try/catch/finally keyword:
```java
try { callMethod(); }
catch ( Exception e ) { log.error( e ); }
finally { cleanup(); }
```

## Method Signatures and Method calls
- Format with space after open parenthesis and before close parenthesis whenever there is any punctuation inside the parentheses:
```java
public static void methodName( int arg1, String arg2 ) {
    callMethod( arg1, arg2 );
    callAnotherMethod(arg3);
    callAgain();
}
```

## Line Length
- Maximum line length is 120 characters; break lines when they would exceed this limit

## Comments
- Remove EVERY comment unless it has the word NOTE in upper-case, or if it is immediately after a `{`
```java
/**
 * NOTE: This docstring should remain.
 */
@Suppress('unused')
public void methodName() {
    // NOTE: This comment should remain.
}



public void methodName() { // this comment is allowed because it is immediately after a squigly open bracket
    { // this comment is ok because it is immediately after '{'
    }
}
```